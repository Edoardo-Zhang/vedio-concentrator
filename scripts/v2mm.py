# -*- coding: utf-8 -*-
"""v2mm.py — 视频下载 + 字幕提取 + 本地语音转写（vedio-concentrator skill 的核心脚本）。

用法:
    python v2mm.py <URL> --outdir <dir>          # 下载视频并提取字幕/转写
    python v2mm.py --local <本地媒体文件> --outdir <dir>
    python v2mm.py --transcribe <dir>            # 对已下载的媒体跑语音识别
    python v2mm.py --check <dir>                 # 只看已产出什么

设计原则: 能拿到平台字幕就绝不上 ASR；ASR 只在没有字幕时兜底。
"""
import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import time

# --------------------------------------------------------------- 路径常量
RT = os.environ.get("VEDIO_CONCENTRATOR_HOME") or os.path.join(
    os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "vedio-concentrator")
BIN = os.path.join(RT, "bin")
MODELS = os.path.join(RT, "models")
DEFAULT_MODEL = os.path.join(MODELS, "faster-whisper-medium")
# 代理：交给共用的 vcproxy 模块（环境变量优先，否则自动探测 + 连通性验证）。
# 别人的代理端口千差万别（7897/7890/10809/1080...），也可能只监听 IPv6 的 ::1，
# 所以不能写死端口，也不该只测 127.0.0.1。模块缺失时退回"只看环境变量"。
def _load_default_proxy():
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import vcproxy
        return vcproxy.detect()
    except Exception:
        return os.environ.get("VEDIO_CONCENTRATOR_PROXY") or None


DEFAULT_PROXY = _load_default_proxy()

PROXY_HOSTS = ("youtube.com", "youtu.be", "googlevideo.com", "ytimg.com",
               "twitter.com", "x.com", "twimg.com", "instagram.com", "facebook.com",
               "vimeo.com", "tiktok.com", "pornhub.com", "reddit.com")

SUBLANG_ORDER = ["zh-Hans", "zh-CN", "zh-Hant", "zh-TW", "zh-HK", "zh", "en", "en-US", "en-GB"]
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")


def log(msg):
    print(msg, flush=True)


def register_cuda_dlls():
    """pip 装的 nvidia-cublas/cudnn 不在 DLL 搜索路径里，ctranslate2 会报
    'cublas64_12.dll is not found'。这里把 nvidia\\*\\bin 注册进去。"""
    if os.name != "nt":
        return []
    try:
        import site
    except Exception:
        return []
    roots = []
    for sp in list(site.getsitepackages()) + [site.getusersitepackages()]:
        nv = os.path.join(sp, "nvidia")
        if os.path.isdir(nv):
            roots.append(nv)
    added = []
    for root in roots:
        for sub in sorted(os.listdir(root)):
            bindir = os.path.join(root, sub, "bin")
            if not os.path.isdir(bindir):
                continue
            try:
                os.add_dll_directory(bindir)
                added.append(bindir)
            except (OSError, AttributeError):
                pass
            # 有些依赖用 PATH 找，双保险
            os.environ["PATH"] = bindir + os.pathsep + os.environ.get("PATH", "")
    return added


def die(msg, code=1):
    log("!! " + msg)
    sys.exit(code)


def tool(name):
    """优先用运行时自带的二进制。"""
    exe = os.path.join(BIN, name + ".exe")
    if os.path.exists(exe):
        return exe
    found = shutil.which(name)
    if found:
        return found
    if name in ("ffmpeg", "ffprobe"):
        die("找不到 %s。请先运行 install_runtime.py 安装。" % name)
    return name


def ffprobe_duration(path):
    try:
        r = subprocess.run([tool("ffprobe"), "-v", "error", "-show_entries",
                            "format=duration", "-of", "default=nw=1:nk=1", path],
                           capture_output=True, text=True)
        return float((r.stdout or "0").strip() or 0)
    except Exception:
        return 0.0


def ts(seconds, comma=False):
    """秒 -> 时间码。先取整毫秒，避免出现 00:00:60,000 这种非法时间码。"""
    ms = int(round(max(0.0, float(seconds)) * 1000))
    h, rem = divmod(ms, 3600000)
    m, rem = divmod(rem, 60000)
    s, msec = divmod(rem, 1000)
    if comma:
        return "%02d:%02d:%02d,%03d" % (h, m, s, msec)
    if h:
        return "%d:%02d:%02d" % (h, m, s)
    return "%02d:%02d" % (m, s)


# ----------------------------------------------------------- URL 短链还原
def resolve_url(url):
    """把抖音/小红书/B站分享短链还原成最终地址。"""
    m = re.search(r"https?://[^\s\u4e00-\u9fff，。、）)】\"']+", url)
    if m:
        url = m.group(0)
    if not re.search(r"(v\.douyin|xhslink|b23\.tv|t\.cn|youtu\.be|dwz\.|url\.cn|tiktok\.com/t/)", url):
        return url
    try:
        r = subprocess.run(["curl", "-sS", "-L", "-o", os.devnull, "--max-time", "25",
                            "--connect-timeout", "10", "-A", UA,
                            "-w", "%{url_effective}", "--noproxy", "*", url],
                           capture_output=True, text=True, timeout=40)
        final = (r.stdout or "").strip()
        if final.startswith("http"):
            log("   短链还原: %s" % final[:120])
            return final
    except Exception as e:
        log("   短链还原失败(%s)，按原样尝试" % e)
    return url


def need_proxy(url, forced):
    if forced:
        return forced
    host = re.sub(r"^https?://", "", url).split("/")[0].lower()
    for h in PROXY_HOSTS:
        if host == h or host.endswith("." + h):
            return DEFAULT_PROXY  # 可能是 None：本机没代理时就是直连
    return None


# --------------------------------------------------------------- yt-dlp
def ydl_opts(a, proxy, outdir, extra=None):
    o = {
        "outtmpl": os.path.join(outdir, "%(id)s.%(ext)s"),
        "writethumbnail": False,
        "writeinfojson": False,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "ignoreerrors": False,
        "retries": 10,
        "fragment_retries": 10,
        "socket_timeout": 30,
        "windowsfilenames": True,
        "trim_file_name": 120,
    }
    if os.environ.get("VEDIO_CONCENTRATOR_DEBUG") == "1":
        o["quiet"] = False
        o["no_warnings"] = False
        o["verbose"] = True
    if proxy:
        o["proxy"] = proxy
    # 让 yt-dlp 用我们自带的 ffmpeg（否则 B 站这类需要合并音视频的站点会直接失败）
    if tool_available("ffmpeg"):
        o["ffmpeg_location"] = BIN if os.path.exists(os.path.join(BIN, "ffmpeg.exe")) else tool("ffmpeg")
    if a.cookies:
        o["cookiefile"] = a.cookies
    if a.cookies_from_browser:
        o["cookiesfrombrowser"] = (a.cookies_from_browser,)
    o.update(extra or {})
    return o


def fmt_chain(a):
    """格式回退链。带 ffmpeg 时可以分开下音视频再合并，否则只能挑单文件格式。"""
    h = a.max_height
    if a.audio_only:
        return ["bestaudio/best"]
    if tool_available("ffmpeg"):
        return [
            "bv*[height<=%d]+ba/b[height<=%d]" % (h, h),
            "bestvideo+bestaudio/best",
            "b[height<=%d]/b" % h,
            "w",
        ]
    # 没有 ffmpeg：只能要已经封装好的单文件格式
    return [
        "b[height<=%d][ext=mp4]/b[height<=%d]/b" % (h, h),
        "best[ext=mp4]/best",
        "w",
    ]


def tool_available(name):
    return bool(shutil.which(name)) or os.path.exists(os.path.join(BIN, name + ".exe"))


def do_download(a, url, proxy, outdir):
    import yt_dlp
    log(">>> 解析并下载: %s" % url)
    meta = {}

    def extract(extra):
        """注意：必须用 download=True。yt-dlp 只在 download=True 时才写字幕文件，
        download=False 是纯元信息查询，连字幕都不会落盘。要阻止下媒体请用 skip_download。"""
        o = ydl_opts(a, proxy, outdir, extra)
        with yt_dlp.YoutubeDL(o) as y:
            return y.extract_info(url, download=True)

    try:
        meta = extract({"skip_download": True, "writesubtitles": False,
                        "writeautomaticsub": False}) or {}
    except Exception as e:
        log("   预取元信息失败(%s)，继续直接下载" % str(e)[:120])
    subs = sub(meta, a.lang)
    log("   标题: %s" % meta.get("title", "?"))
    log("   时长: %s   平台: %s" % (ts(meta.get("duration") or 0), meta.get("extractor_key", "?")))
    log("   可用字幕: %s" % (", ".join(sorted(subs.keys())) or "无"))

    chain = fmt_chain(a)
    errs = []
    for i, f in enumerate(chain, 1):
        extra = {"format": f, "writesubtitles": bool(subs), "writeautomaticsub": bool(subs),
                 "subtitleslangs": pick_langs(subs, a.lang) if subs else [],
                 "subtitlesformat": "srt/vtt/best"}
        if a.no_video:
            extra["skip_download"] = True
        log("   尝试格式 %d/%d: %s" % (i, len(chain), f))
        try:
            with yt_dlp.YoutubeDL(ydl_opts(a, proxy, outdir, extra)) as y:
                info = y.extract_info(url, download=True)
            if info and not meta:
                meta = info
            log("   下载完成")
            return meta, None
        except Exception as e:
            msg = str(e).split("\n")[0][:200]
            errs.append("格式 %s -> %s" % (f, msg))
            log("     失败: %s" % msg)

    hint = ""
    low = " ".join(errs).lower()
    if "sign in" in low or "bot" in low:
        if DEFAULT_PROXY:
            hint = ("（该站点通常需要代理和 cookie：--proxy %s --cookies-from-browser edge）"
                    % DEFAULT_PROXY)
        else:
            hint = ("（该站点通常需要代理和 cookie。本机没探测到代理，可用 "
                    "--proxy http://127.0.0.1:端口 指定，并加 --cookies-from-browser edge）")
    elif "no video formats" in low or "login" in low or "cookie" in low:
        hint = "（该站需要登录 cookie: --cookies-from-browser chrome）"
    return meta, ("所有格式尝试均失败:\n  " + "\n  ".join(errs) + "\n  " + hint)


def sub(info, lang_wanted):
    d = {}
    for k in ("subtitles", "automatic_captions"):
        for kk, vv in (info.get(k) or {}).items():
            d.setdefault(kk, []).extend(vv or [])
    return d


def pick_langs(available, wanted):
    order = [x.strip() for x in (wanted or "").split(",") if x.strip()] or SUBLANG_ORDER
    picked = [l for l in order if l in available]
    if not picked:  # 模糊匹配 zh-Hans <-> zh-CN 之类的差异
        for want in order:
            for have in sorted(available.keys()):
                if have == want or have.startswith(want + "-") or want.startswith(have + "-"):
                    picked.append(have)
    if not picked:
        picked = sorted(available.keys())[:3]
    seen, out = set(), []
    for p in picked:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out[:5]


# ------------------------------------------------------- 字幕 -> 转写文本
def srt_to_lines(path):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        raw = f.read()
    raw = raw.replace("\ufeff", "")
    out = []
    for block in re.split(r"\n\s*\n", raw):
        lines = [l.strip() for l in block.strip().splitlines() if l.strip()]
        if not lines:
            continue
        tm = None
        body = []
        for l in lines:
            if tm is None and "-->" in l:
                mm = re.search(r"(\d+):(\d+):(\d+)[,.](\d+)", l)
                if mm:
                    h, m, s, ms = (int(x) for x in mm.groups())
                    tm = h * 3600 + m * 60 + s + ms / 1000.0
                continue
            if l.isdigit():
                continue
            body.append(re.sub(r"<[^>]+>", "", l))
        if body:
            out.append((tm if tm is not None else 0.0, " ".join(body)))
    return out


def dedupe(pairs):
    """去掉自动字幕常见的重复行与空行。"""
    res = []
    for t, s in pairs:
        s = re.sub(r"\s+", " ", s).strip()
        if not s:
            continue
        if res and (s == res[-1][1] or (len(s) < 12 and s in res[-1][1])):
            continue
        if res and s.startswith(res[-1][1]) and len(s) - len(res[-1][1]) < 6:
            res[-1] = (res[-1][0], s)
            continue
        res.append((t, s))
    return res


def write_transcript(outdir, pairs, source):
    pairs = dedupe(pairs)
    txt = os.path.join(outdir, "transcript.txt")
    srt = os.path.join(outdir, "transcript.srt")
    with open(txt, "w", encoding="utf-8") as f:
        f.write("# 转写来源: %s\n# 行数: %d\n\n" % (source, len(pairs)))
        for t, s in pairs:
            f.write("[%s] %s\n" % (ts(t), s))
    with open(srt, "w", encoding="utf-8") as f:
        for i, (t, s) in enumerate(pairs, 1):
            end = t + max(1.2, min(8.0, len(s) / 6.0))
            f.write("%d\n%s --> %s\n%s\n\n" % (i, ts(t, True), ts(end, True), s))
    chars = sum(len(s) for _, s in pairs)
    log(">>> 转写文本: %s (%d 行, %d 字)" % (txt, len(pairs), chars))
    return txt, chars


def convert_subs_to_srt(outdir):
    """把 yt-dlp 下到的任意字幕格式统一成 srt。"""
    got = []
    subs = [p for p in glob.glob(os.path.join(outdir, "*.vtt"))
            + glob.glob(os.path.join(outdir, "*.srt"))
            + glob.glob(os.path.join(outdir, "*.json3"))
            + glob.glob(os.path.join(outdir, "*.srv3"))]
    for p in subs:
        base, ext = os.path.splitext(p)
        if ext.lower() == ".srt":
            got.append(p)
            continue
        target = base + ".srt"
        if ext.lower() == ".json3":
            try:
                with open(p, "r", encoding="utf-8", errors="replace") as f:
                    data = json.load(f)
                pairs = []
                for ev in data.get("events", []):
                    t = (ev.get("tStartMs") or 0) / 1000.0
                    seg = "".join(s.get("utf8", "") for s in (ev.get("segs") or []))
                    if seg.strip():
                        pairs.append((t, seg))
                with open(target, "w", encoding="utf-8") as f:
                    for i, (t, s) in enumerate(pairs, 1):
                        f.write("%d\n%s --> %s\n%s\n\n" % (
                            i, ts(t, True), ts(t + 2, True), s.replace("\n", " ")))
                got.append(target)
                continue
            except Exception as e:
                log("   json3 解析失败(%s)，改用 ffmpeg" % e)
        r = subprocess.run([tool("ffmpeg"), "-y", "-loglevel", "error", "-i", p, target],
                           capture_output=True, text=True)
        if r.returncode == 0 and os.path.exists(target):
            got.append(target)
        else:
            log("   字幕转换失败: %s %s" % (os.path.basename(p), (r.stderr or "")[:120]))
    return got


def pick_best_srt(outdir, lang_wanted):
    srt_files = convert_subs_to_srt(outdir)
    if not srt_files:
        return None
    order = [x.strip() for x in (lang_wanted or "").split(",") if x.strip()] or SUBLANG_ORDER
    def rank(p):
        b = os.path.basename(p).lower()
        for i, l in enumerate(order):
            if "." + l.lower() + "." in b:
                return i
        return len(order) + 1
    srt_files.sort(key=lambda p: (rank(p), -os.path.getsize(p)))
    return srt_files[0]


# --------------------------------------------------------------------- ASR
def find_media(outdir, want_audio=False):
    vids, auds = [], []
    for ext in ("mp4", "mkv", "webm", "flv", "mov", "avi", "m4a", "mp3", "wav", "opus", "aac", "m4b"):
        for p in glob.glob(os.path.join(outdir, "*." + ext)):
            if os.path.basename(p).startswith("audio."):
                auds.append(p)
            elif ext in ("m4a", "mp3", "wav", "opus", "aac", "m4b"):
                auds.append(p)
            else:
                vids.append(p)
    pool = (auds + vids) if want_audio else (vids + auds)
    if not pool:
        return None
    pool.sort(key=lambda p: -os.path.getsize(p))
    return pool[0]


def to_wav(media, outdir):
    wav = os.path.join(outdir, "audio16k.wav")
    if os.path.exists(wav) and os.path.getsize(wav) > 1024:
        return wav
    log(">>> 抽取 16k 单声道音频（ffmpeg）")
    r = subprocess.run([tool("ffmpeg"), "-y", "-loglevel", "error", "-i", media,
                        "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", wav],
                       capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(wav):
        die("ffmpeg 抽音频失败: %s" % (r.stderr or "")[:300])
    log("    %.1f MB, 时长 %s" % (os.path.getsize(wav) / 1048576.0, ts(ffprobe_duration(wav))))
    return wav


def do_asr(a, outdir):
    cuda_dirs = register_cuda_dlls()
    from faster_whisper import WhisperModel
    media = a.media or find_media(outdir, want_audio=True)
    if not media or not os.path.exists(media):
        die("目录里没有可转写的媒体文件: %s" % outdir)
    wav = to_wav(media, outdir)

    model_path = a.model or DEFAULT_MODEL
    if not os.path.exists(os.path.join(model_path, "model.bin")):
        die("模型不存在: %s\n先运行 install_runtime.py，或用 --model 指定其它 faster-whisper 模型目录"
            % model_path)

    dev, ct = a.device, a.compute_type
    if dev == "auto":
        try:
            import ctranslate2
            dev = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
        except Exception:
            dev = "cpu"
    if ct == "auto":
        ct = "float16" if dev == "cuda" else "int8"
    log(">>> 语音识别: model=%s device=%s compute=%s%s" % (
        os.path.basename(model_path), dev, ct,
        (" (CUDA DLL: %d 个目录)" % len(cuda_dirs)) if cuda_dirs else ""))

    t0 = time.time()
    try:
        model = WhisperModel(model_path, device=dev, compute_type=ct, cpu_threads=os.cpu_count() or 8)
    except Exception as e:
        log("   %s 初始化失败(%s)，回落 CPU/int8" % (dev, str(e)[:120]))
        dev, ct = "cpu", "int8"
        model = WhisperModel(model_path, device="cpu", compute_type="int8",
                             cpu_threads=os.cpu_count() or 8)

    def run(vad):
        segs, inf = model.transcribe(
            wav,
            language=(a.lang.split(",")[0] if a.lang else None),
            beam_size=a.beam_size,
            vad_filter=vad,
            vad_parameters={"min_silence_duration_ms": 500} if vad else None,
            condition_on_previous_text=False,
            initial_prompt=a.prompt or None,
        )
        return list(segs), inf

    total = ffprobe_duration(wav) or 1.0

    def collect(segments):
        """把 segment 归并成 ~100 字 / ~40 秒的块，长视频才不至于碎成上千行。"""
        out, buf, start, last_log = [], "", None, -1
        for seg in segments:
            text = re.sub(r"\s+", " ", seg.text).strip()
            if not text:
                continue
            if start is None:
                start = seg.start
            buf = (buf + " " + text).strip() if buf else text
            if len(buf) >= 100 or (seg.end - start) > 40:
                out.append((start, buf))
                buf, start = "", None
            minute = int(seg.end // 60)
            if minute > last_log:
                last_log = minute
                el = time.time() - t0
                eta = (el / max(seg.end, 1)) * max(total - seg.end, 0)
                log("    进度 %.1f%%  已用 %s  预计剩余 %s" % (
                    min(99.9, seg.end / total * 100), ts(el), ts(eta)))
        if buf:
            out.append((start or 0.0, buf))
        return out

    segments, info = run(True)
    pairs = collect(segments)
    if not pairs:
        # 纯音乐 / 无人声 / VAD 误判时全被过滤掉，关掉 VAD 再试一次
        log("    VAD 过滤后没有内容，关闭 VAD 重试一次")
        segments, info = run(False)
        pairs = collect(segments)
    if not pairs:
        log("    该媒体里没有可识别的语音（纯音乐或无对白？）")

    log(">>> 识别完成: %d 段, 语言=%s(%.2f), 耗时 %s (%.2fx 实时)" % (
        len(pairs), info.language, info.language_probability, ts(time.time() - t0),
        total / max(time.time() - t0, 1e-6)))
    return write_transcript(outdir, pairs, "faster-whisper %s / %s / %s" % (
        os.path.basename(model_path), dev, ct))


# ------------------------------------------------------------------- meta
def write_meta(outdir, meta, url, extra=None):
    keep = ["id", "title", "uploader", "channel", "upload_date", "duration",
            "view_count", "like_count", "description", "webpage_url", "extractor_key",
            "tags", "categories", "thumbnail"]
    slim = {k: meta.get(k) for k in keep if meta.get(k) is not None}
    if slim.get("description") and len(str(slim["description"])) > 4000:
        slim["description"] = str(slim["description"])[:4000] + "…"
    slim["source_url"] = url
    slim.update(extra or {})
    p = os.path.join(outdir, "meta.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(slim, f, ensure_ascii=False, indent=2)
    log(">>> 元信息: %s" % p)
    return slim


# ------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="视频下载 + 字幕/转写（vedio-concentrator）")
    ap.add_argument("url", nargs="?", help="视频链接")
    ap.add_argument("--local", help="本地媒体文件（跳过下载）")
    ap.add_argument("--outdir", "-o", default=".", help="输出目录")
    ap.add_argument("--transcribe", action="store_true", help="对已下载媒体跑 ASR")
    ap.add_argument("--check", action="store_true", help="只报告目录里已有什么")
    ap.add_argument("--media", help="指定要转写的媒体文件")
    ap.add_argument("--cookies")
    ap.add_argument("--cookies-from-browser", dest="cookies_from_browser")
    ap.add_argument("--proxy", help="不传则按站点自动判断")
    ap.add_argument("--no-proxy", action="store_true")
    ap.add_argument("--lang", default="", help="字幕/语音语言优先级，如 zh,en")
    ap.add_argument("--max-height", type=int, default=1080)
    ap.add_argument("--audio-only", action="store_true")
    ap.add_argument("--no-video", action="store_true", help="只拿字幕和元信息")
    ap.add_argument("--model", help="faster-whisper 模型目录")
    ap.add_argument("--device", default="auto", choices=["auto", "cuda", "cpu"])
    ap.add_argument("--compute-type", default="auto")
    ap.add_argument("--beam-size", type=int, default=5)
    ap.add_argument("--prompt", help="ASR 初始提示（专有名词能显著提升准确率）")
    a = ap.parse_args()

    outdir = os.path.abspath(a.outdir)
    os.makedirs(outdir, exist_ok=True)

    if a.check:
        for p in sorted(glob.glob(os.path.join(outdir, "*"))):
            log("  %9.2f MB  %s" % (os.path.getsize(p) / 1048576.0, os.path.basename(p)))
        return 0

    if a.transcribe:
        do_asr(a, outdir)
        return 0

    if a.local:
        src = os.path.abspath(a.local)
        if not os.path.exists(src):
            die("本地文件不存在: %s" % src)
        dst = os.path.join(outdir, os.path.basename(src))
        if os.path.abspath(src) != os.path.abspath(dst):
            shutil.copy2(src, dst)
        log(">>> 本地媒体: %s" % dst)
        write_meta(outdir, {"title": os.path.splitext(os.path.basename(src))[0]},
                   "file://" + src)
        log(">>> 就该跑 ASR 了: python v2mm.py --transcribe \"%s\"" % outdir)
        return 0

    if not a.url:
        ap.print_help()
        return 2

    url = resolve_url(a.url)
    proxy = None if a.no_proxy else need_proxy(url, a.proxy)
    if proxy:
        log(">>> 该站点走代理: %s" % proxy)

    meta, err = do_download(a, url, proxy, outdir)
    if err and not find_media(outdir):
        die(err)
    if meta:
        write_meta(outdir, meta, url, {"proxy_used": proxy, "asr": None})

    media = find_media(outdir, want_audio=True)
    log(">>> 下载产物: %s" % (os.path.basename(media) if media else "（无媒体文件）"))

    srt = pick_best_srt(outdir, a.lang)
    if srt:
        pairs = srt_to_lines(srt)
        if pairs:
            log(">>> 使用平台字幕: %s" % os.path.basename(srt))
            txt, chars = write_transcript(outdir, pairs, "平台字幕 %s" % os.path.basename(srt))
            if chars >= 120:
                log(">>> 字幕可用，无需 ASR。下一步：读 transcript.txt 写 outline.md")
                return 0
            log(">>> 字幕内容过少(%d 字)，改走 ASR" % chars)
    else:
        log(">>> 没有可用字幕")

    if a.no_video:
        die("没有字幕且指定了 --no-video，无法继续。去掉 --no-video 重跑。")

    do_asr(a, outdir)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        log("中断")
        sys.exit(130)
