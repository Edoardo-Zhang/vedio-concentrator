# -*- coding: utf-8 -*-
"""vedio-concentrator 运行时安装（幂等，可重复运行）。

安装内容:
  1. Python 依赖: yt-dlp, faster-whisper, av, requests (+ 可选 nvidia cuBLAS/cuDNN)
  2. faster-whisper medium 模型 (~1.5 GB, hf-mirror)
  3. ffmpeg + ffprobe 静态二进制
  4. markmap 离线渲染库
  5. 自检
"""
import json
import os
import re
import subprocess
import sys
import tarfile
import time
import zipfile

RT = os.environ.get("VEDIO_CONCENTRATOR_HOME") or os.path.join(
    os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "vedio-concentrator")
LOGDIR = os.path.join(RT, "logs")
CACHE = os.path.join(RT, "cache")
os.makedirs(LOGDIR, exist_ok=True)
os.makedirs(CACHE, exist_ok=True)
LOG = os.path.join(LOGDIR, "install.log")
HF = "https://hf-mirror.com/Systran/faster-whisper-medium/resolve/main"
PYPI = "https://pypi.tuna.tsinghua.edu.cn/simple"


def detect_proxy():
    """跟 v2mm.py 用同一套探测逻辑；模块缺失时退回环境变量。"""
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import vcproxy
        return vcproxy.detect(verbose=True)
    except Exception:
        return os.environ.get("VEDIO_CONCENTRATOR_PROXY") or None


PROXY = detect_proxy()


def log(msg):
    line = "[%s] %s" % (time.strftime("%H:%M:%S"), msg)
    print(line, flush=True)
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def human(n):
    n = float(n)
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024 or u == "GB":
            return "%.2f %s" % (n, u)
        n /= 1024.0


def probe(url, proxy=None, secs=10):
    a = ["curl", "-sS", "-L", "-o", os.devnull, "--max-time", str(secs),
         "--connect-timeout", "8", "-w", "%{speed_download} %{http_code}"]
    a += ["-x", proxy] if proxy else ["--noproxy", "*"]
    a.append(url)
    try:
        r = subprocess.run(a, capture_output=True, text=True, timeout=secs + 25)
        p = (r.stdout or "").split()
        if len(p) >= 2:
            return float(p[0]), p[1]
    except Exception:
        pass
    return 0.0, "ERR"


def head_size(url, proxy=None):
    """取服务器端真实大小（字节）；HF 会 302 到 CDN，所以用 -L 跟着走。"""
    a = ["curl", "-sS", "-L", "-I", "--max-time", "30", "--connect-timeout", "10"]
    a += ["-x", proxy] if proxy else ["--noproxy", "*"]
    a.append(url)
    try:
        r = subprocess.run(a, capture_output=True, text=True, timeout=45)
        sizes = re.findall(r"(?im)^content-length:\s*(\d+)", r.stdout or "")
        return int(sizes[-1]) if sizes else None
    except Exception:
        return None


def fetch(out, expect, urls, quiet=False):
    """urls: [(url, proxy_or_None)] — 测速选源 + 断点续传 + 大小校验。

    expect 为 None 时会尝试从服务器读取真实大小，避免写死数字写错。
    """
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    name = os.path.basename(out)
    best, sp_best = None, 0.0
    for url, proxy in urls:
        if expect is None:
            expect = head_size(url, proxy)
        sp, code = probe(url, proxy)
        if not quiet:
            log("  候选 %10s/s http=%-3s %s" % (human(sp), code, url[:78]))
        if code == "200" and sp > sp_best:
            best, sp_best = (url, proxy), sp
    if not best:
        log("  !! 无可用源: %s" % name)
        return False
    if expect and os.path.exists(out) and os.path.getsize(out) == expect:
        if not quiet:
            log("  已存在且大小正确（%.1f MB），跳过" % (expect / 1048576.0))
        return True
    url, proxy = best
    if not quiet:
        log("  选用%s (%s)%s" % ("代理" if proxy else "直连", human(sp_best),
                                 "，期望 %.1f MB" % (expect / 1048576.0) if expect else ""))
    for _ in range(4):
        a = ["curl", "-L", "-C", "-", "--retry", "15", "--retry-delay", "4",
             "--retry-all-errors", "-sS", "-o", out, url]
        a += ["-x", proxy] if proxy else ["--noproxy", "*"]
        subprocess.run(a)
        sz = os.path.getsize(out) if os.path.exists(out) else 0
        if not quiet:
            log("  落盘 %.1f MB" % (sz / 1048576.0))
        if not expect or sz == expect:
            break
    ok = (not expect) or (os.path.exists(out) and os.path.getsize(out) == expect)
    if not ok:
        log("  FAIL %s（期望 %s，实际 %s）" % (name, expect,
              os.path.getsize(out) if os.path.exists(out) else 0))
    return ok


# ------------------------------------------------------------------ 1. pip
def pip(*pkgs, index=PYPI):
    a = [sys.executable, "-m", "pip", "install", "--upgrade",
         "--disable-pip-version-check", "-q"]
    if index:
        a += ["-i", index]
    a += list(pkgs)
    r = subprocess.run(a, capture_output=True, text=True)
    return r.returncode, (r.stderr or "").strip()


def do_pip():
    log("=== [1/5] Python 依赖 ===")
    ok = True
    for pkgs in (["yt-dlp"], ["faster-whisper", "av", "requests"]):
        rc, err = pip(*pkgs)
        if rc != 0:
            rc, err = pip(*pkgs, index=None)
        log("  %s -> rc=%d %s" % (" ".join(pkgs), rc, err[-200:] if err else ""))
        ok &= rc == 0
    if os.environ.get("VEDIO_CONCENTRATOR_SKIP_CUDA") != "1":
        log("  可选: CUDA 运行时（cuBLAS + cuDNN9，失败不影响 CPU 转写）")
        rc, err = pip("nvidia-cublas-cu12", "nvidia-cudnn-cu12==9.*")
        if rc != 0:
            rc, err = pip("nvidia-cublas-cu12", "nvidia-cudnn-cu12==9.*", index=None)
        log("    CUDA 运行时 rc=%d" % rc)
    return ok


# ------------------------------------------------------------- 2. ASR 模型
def do_model():
    log("=== [2/5] faster-whisper medium 模型 (~1.5GB) ===")
    d = os.path.join(RT, "models", "faster-whisper-medium")
    files = ["model.bin", "config.json", "tokenizer.json", "vocabulary.txt"]
    ok = True
    for name in files:
        cands = [("%s/%s?download=true" % (HF, name), None)]
        if PROXY:
            # 没探测到代理时不要塞 -x None，否则 curl 直接报错
            cands.append(("%s/%s" % (HF, name), PROXY))
        ok &= fetch(os.path.join(d, name), None, cands)
    return ok


# ---------------------------------------------------------------- 3. ffmpeg
def do_ffmpeg():
    log("=== [3/5] ffmpeg / ffprobe ===")
    bindir = os.path.join(RT, "bin")
    os.makedirs(bindir, exist_ok=True)
    if all(os.path.exists(os.path.join(bindir, e)) for e in ("ffmpeg.exe", "ffprobe.exe")):
        log("  已存在，跳过")
        return True
    zpath = os.path.join(CACHE, "ffmpeg.zip")
    url = ("https://github.com/GyanD/codexffmpeg/releases/download/7.1/"
           "ffmpeg-7.1-essentials_build.zip")
    # GitHub 直连常常不通，代理能通就用；两条都给，fetch 会按实测速度选
    cands = [(url, None)]
    if PROXY:
        cands.append((url, PROXY))
    if not fetch(zpath, None, cands):
        return False
    with zipfile.ZipFile(zpath) as z:
        for m in z.namelist():
            base = os.path.basename(m).lower()
            if base in ("ffmpeg.exe", "ffprobe.exe"):
                with z.open(m) as src, open(os.path.join(bindir, base), "wb") as dst:
                    dst.write(src.read())
                log("  提取 %s" % base)
    try:
        os.remove(zpath)
    except OSError:
        pass
    return all(os.path.exists(os.path.join(bindir, e)) for e in ("ffmpeg.exe", "ffprobe.exe"))


# --------------------------------------------------------------- 4. markmap
MM_VERSION = "0.18.12"


def do_markmap():
    log("=== [4/5] markmap 离线渲染库 ===")
    d = os.path.join(RT, "markmap")
    os.makedirs(d, exist_ok=True)
    specs = [("markmap-autoloader", MM_VERSION), ("markmap-lib", MM_VERSION),
             ("markmap-view", MM_VERSION), ("markmap-common", "0.18.9"),
             ("markmap-toolbar", MM_VERSION), ("d3", None), ("katex", None)]
    ok = True
    for name, ver in specs:
        outdir = os.path.join(d, name)
        marker = os.path.join(outdir, "dist")
        if os.path.isdir(marker) and os.listdir(marker):
            log("  %s 已存在，跳过" % name)
            continue
        if ver is None:
            try:
                meta = json.loads(subprocess.run(
                    ["curl", "-sS", "-L", "--noproxy", "*", "--max-time", "30",
                     "https://registry.npmmirror.com/%s/latest" % name],
                    capture_output=True, text=True).stdout)
                ver = meta["version"]
            except Exception as e:
                log("  !! 取 %s 版本失败: %s" % (name, e))
                ok = False
                continue
        base = name.split("/")[-1]
        url = "https://registry.npmmirror.com/%s/-/%s-%s.tgz" % (name, base, ver)
        tgz = os.path.join(CACHE, "%s-%s.tgz" % (base, ver))
        if not fetch(tgz, None, [(url, None)], quiet=True):
            ok = False
            continue
        os.makedirs(outdir, exist_ok=True)
        try:
            with tarfile.open(tgz) as t:
                for m in t.getmembers():
                    if m.isfile() and m.name.startswith("package/"):
                        rel = m.name[len("package/"):]
                        dst = os.path.join(outdir, rel)
                        os.makedirs(os.path.dirname(dst), exist_ok=True)
                        with t.extractfile(m) as src, open(dst, "wb") as fo:
                            fo.write(src.read())
        except Exception as e:
            log("  !! 解包 %s 失败: %s" % (name, e))
            ok = False
            continue
        log("  %s@%s 解包完成" % (name, ver))
    return ok


# ------------------------------------------------------------------ 5. 自检
def do_check():
    log("=== [5/5] 自检 ===")
    rows = []
    try:
        r = subprocess.run([sys.executable, "-c",
                            "import yt_dlp, faster_whisper;"
                            "print('yt-dlp', yt_dlp.version.__version__)"],
                           capture_output=True, text=True)
        rows.append(("yt-dlp + faster-whisper", r.returncode == 0, r.stdout.strip()))
    except Exception as e:
        rows.append(("yt-dlp + faster-whisper", False, str(e)))
    for exe in ("ffmpeg.exe", "ffprobe.exe"):
        rows.append((exe, os.path.exists(os.path.join(RT, "bin", exe)), ""))
    mb = os.path.join(RT, "models", "faster-whisper-medium", "model.bin")
    rows.append(("medium 模型", os.path.exists(mb),
                 "%.1f MB" % (os.path.getsize(mb) / 1048576.0) if os.path.exists(mb) else "缺失"))
    mm = os.path.join(RT, "markmap", "markmap-autoloader", "dist", "index.js")
    rows.append(("markmap-autoloader", os.path.exists(mm), ""))
    for name, good, extra in rows:
        log("  [%s] %-26s %s" % ("OK" if good else "!!", name, extra))
    return all(r[1] for r in rows)


if __name__ == "__main__":
    log("=" * 64)
    log("vedio-concentrator 运行时安装 -> %s" % RT)
    a = do_pip()
    b = do_model()
    c = do_ffmpeg()
    d = do_markmap()
    e = do_check()
    good = all([a, b, c, d, e])
    log("=" * 64)
    log("安装结果: %s" % ("全部成功" if good else "有失败项，见上"))
    with open(os.path.join(LOGDIR, "install.done"), "w", encoding="utf-8") as f:
        f.write("ok" if good else "partial")
    sys.exit(0 if good else 1)
