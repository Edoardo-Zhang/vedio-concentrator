# -*- coding: utf-8 -*-
"""安装 / 修复 vedio-concentrator skill（幂等，可反复运行）。

自动识别两种目录形态：
  仓库形态   <root>/scripts/setup.py   + <root>/skill/SKILL.md
  已安装形态 <skills>/vedio-concentrator/setup.py + SKILL.md（同目录）

用法:
    python setup.py                # 装 skill + 装运行时
    python setup.py --skill-only   # 只复制文档和脚本
    python setup.py --runtime-only # 只装运行时（模型/ffmpeg/markmap）
    python setup.py --check        # 只自检，不安装
    python setup.py --dest <目录>  # 指定 skill 安装位置
"""
import argparse
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)  # 仓库根；已安装形态下等于 skill 目录

# 文档目录：仓库形态在 ../skill，已安装形态就在当前目录
DOC_DIR = os.path.join(ROOT, "skill")
if not os.path.exists(os.path.join(DOC_DIR, "SKILL.md")):
    DOC_DIR = HERE
    ROOT = HERE

SKILL_NAME = "vedio-concentrator"
DEFAULT_DEST = os.path.join(os.path.expanduser("~"), ".cursor", "skills", SKILL_NAME)
RT = os.environ.get("VEDIO_CONCENTRATOR_HOME") or os.path.join(
    os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), SKILL_NAME)

DOC_FILES = ["SKILL.md", "reference.md", "README.md"]
# 装进 skill/scripts/ 的运行时脚本
TOOL_FILES = ["v2mm.py", "render_mindmap.py", "setup_check.py", "install_runtime.py",
              "vcproxy.py"]


def log(msg):
    print(msg, flush=True)


def copy_retry(src, dst, tries=8, delay=0.4):
    """带重试的复制。

    刚解压出来的文件常被杀软/搜索索引器短暂占用，直接复制会抛
    PermissionError(WinError 32)。这里退避重试，避免用户第一次装就失败。
    """
    last = None
    for i in range(tries):
        try:
            shutil.copy2(src, dst)
            return True
        except PermissionError as e:
            last = e
            time.sleep(delay * (i + 1) / 2.0)
        except OSError as e:
            last = e
            if getattr(e, "winerror", None) not in (32, 33):
                raise
            time.sleep(delay * (i + 1) / 2.0)
    log("  !! 复制失败（文件被其它程序占用）: %s -> %s" % (src, dst))
    log("     %s" % last)
    log("     提示: 关掉正在扫描该目录的杀毒软件/资源管理器预览后重试。")
    return False


def find_script(name):
    """脚本可能在 scripts/ 子目录，也可能和本文件同级。"""
    for cand in (os.path.join(HERE, name), os.path.join(ROOT, "scripts", name),
                 os.path.join(ROOT, name)):
        if os.path.exists(cand):
            return cand
    return None


def install_skill(dest):
    log("=== 安装 skill -> %s ===" % dest)
    os.makedirs(os.path.join(dest, "scripts"), exist_ok=True)

    n = 0
    bad = []
    for name in DOC_FILES:
        src = os.path.join(DOC_DIR, name)
        if os.path.exists(src):
            if copy_retry(src, os.path.join(dest, name)):
                log("  %s" % name)
                n += 1
            else:
                bad.append(name)
    for name in TOOL_FILES:
        src = find_script(name)
        if not src:
            log("  !! 找不到 %s" % name)
            bad.append(name)
            continue
        if copy_retry(src, os.path.join(dest, "scripts", name)):
            log("  scripts/%s" % name)
            n += 1
        else:
            bad.append(name)
    # setup.py 自己 + 一键安装脚本
    if copy_retry(os.path.abspath(__file__), os.path.join(dest, "setup.py")):
        n += 1
    else:
        bad.append("setup.py")
    for extra in ("install.cmd", "install.ps1"):
        src = find_script(extra)
        if src:
            if copy_retry(src, os.path.join(dest, extra)):
                log("  %s" % extra)
                n += 1
            else:
                bad.append(extra)
    log("  共 %d 个文件%s" % (n, ("，失败 %d 个" % len(bad)) if bad else ""))
    return not bad


def install_runtime():
    log("=== 安装运行时 -> %s ===" % RT)
    installer = find_script("install_runtime.py")
    if not installer:
        log("!! 找不到 install_runtime.py")
        return 1
    env = dict(os.environ)
    env.setdefault("PYTHONIOENCODING", "utf-8")
    return subprocess.call([sys.executable, installer], env=env)


def selfcheck():
    checker = find_script("setup_check.py")
    if not checker:
        log("!! 找不到 setup_check.py")
        return 1
    return subprocess.call([sys.executable, checker])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skill-only", action="store_true")
    ap.add_argument("--runtime-only", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--dest", default=DEFAULT_DEST)
    a = ap.parse_args()

    if a.check:
        return selfcheck()

    rc = 0
    if not a.runtime_only:
        if not install_skill(a.dest):
            # 文件复制没成功就不要接着装运行时，否则用户拿到的是半成品
            log("!! skill 文件没复制完，已中止。")
            return 1
    if not a.skill_only:
        rc = install_runtime()

    log("")
    log("skill:   %s" % a.dest)
    log("runtime: %s" % RT)
    log("自检:    python \"%s\"" % os.path.join(a.dest, "scripts", "setup_check.py"))
    return rc


if __name__ == "__main__":
    sys.exit(main())
