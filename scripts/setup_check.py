# -*- coding: utf-8 -*-
"""setup_check.py — 检查 vedio-concentrator 运行时是否就绪，并报告 GPU 可用性。

用法: python setup_check.py [--json]
"""
import glob
import importlib
import json
import os
import subprocess
import sys

RT = os.environ.get("VEDIO_CONCENTRATOR_HOME") or os.path.join(
    os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "vedio-concentrator")


def p(*a):
    return os.path.join(RT, *a)


def mod_ok(name):
    try:
        importlib.import_module(name)
        return True, ""
    except Exception as e:
        return False, str(e)[:120]


def main():
    rows = []

    for m in ("yt_dlp", "faster_whisper", "av", "requests"):
        ok, err = mod_ok(m)
        rows.append(("python: " + m, ok, err))

    try:
        import yt_dlp
        rows.append(("yt-dlp 版本", True, yt_dlp.version.__version__))
    except Exception:
        pass

    for exe in ("ffmpeg.exe", "ffprobe.exe"):
        f = p("bin", exe)
        rows.append((exe, os.path.exists(f), f if os.path.exists(f) else "缺失"))

    mb = p("models", "faster-whisper-medium", "model.bin")
    if os.path.exists(mb):
        rows.append(("ASR 模型 medium", True, "%.1f MB" % (os.path.getsize(mb) / 1048576.0)))
    else:
        rows.append(("ASR 模型 medium", False, "缺失，跑 install_runtime.py"))

    other = [os.path.basename(os.path.dirname(x)) for x in
             glob.glob(p("models", "*", "model.bin"))]
    if other:
        rows.append(("已下载的其它模型", True, ", ".join(sorted(set(other)))))

    rows.append(("markmap 渲染库",
                 os.path.isdir(p("markmap", "markmap-lib")),
                 p("markmap")))

    gpu_ok, gpu_msg = False, "CPU only"
    try:
        import ctranslate2
        n = ctranslate2.get_cuda_device_count()
        gpu_ok = n > 0
        gpu_msg = "CUDA 设备 %d 个" % n
        if n > 0:
            try:
                from faster_whisper import WhisperModel
                WhisperModel(p("models", "faster-whisper-medium"), device="cuda",
                             compute_type="float16")
                gpu_msg += "，float16 初始化成功，走 GPU"
            except Exception as e:
                gpu_ok = False
                gpu_msg += "，但初始化失败: %s" % str(e)[:100]
    except Exception as e:
        gpu_msg = "ctranslate2 不可用: %s" % str(e)[:80]
    rows.append(("GPU 加速", gpu_ok, gpu_msg))

    for name, ok, extra in rows:
        print("  [%s] %-24s %s" % ("OK" if ok else "!!", name, extra))

    required = [r for r in rows if r[0].startswith(("python:", "ffmpeg", "ffprobe",
                                                   "ASR 模型", "markmap", "yt-dlp 版本"))]
    ready = all(r[1] for r in required)
    print()
    print("运行时目录: %s" % RT)
    print("结论: %s" % ("就绪 ✓" if ready else "未就绪 ✗ — 运行 install_runtime.py"))
    if "--json" in sys.argv:
        print(json.dumps({r[0]: {"ok": r[1], "info": r[2]} for r in rows},
                         ensure_ascii=False, indent=2))
    return 0 if ready else 1


if __name__ == "__main__":
    sys.exit(main())
