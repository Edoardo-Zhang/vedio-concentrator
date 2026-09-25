# -*- coding: utf-8 -*-
"""build_dist.py — 把本仓库打包成可分发 zip（含 SHA256 清单）。

产出:
  dist/vedio-concentrator-repo.zip      仓库形态：scripts/ + skill/，直接推 GitHub
  dist/vedio-concentrator-bundle.zip    解压即装：顶层直接是 install.cmd + setup.py
  dist/SHA256SUMS.txt                   两个包的校验值

用法: python build_dist.py
"""
import hashlib
import os
import shutil
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DIST = os.path.join(ROOT, "dist")

SKILL_NAME = "vedio-concentrator"
VERSION = "1.0.1"

DOC_FILES = ["SKILL.md", "reference.md"]
SCRIPT_FILES = ["v2mm.py", "vcproxy.py", "render_mindmap.py", "setup_check.py",
                "install_runtime.py", "setup.py", "install.cmd", "install.ps1",
                "bootstrap.ps1", "build_dist.py"]
ROOT_FILES = ["README.md", "LICENSE", ".gitignore", "GITHUB-GUIDE.md"]


def log(m):
    print(m, flush=True)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for blk in iter(lambda: f.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def decode_any(raw):
    """按常见编码依次尝试解码源码文件（UTF-8 / GBK），保证能正确读出中文。"""
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig")
    for enc in ("utf-8", "cp936"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def copy(src, dst):
    """复制并规范化行尾与编码，避免 Windows 上出现解析问题。

    - .ps1  -> UTF-8 with BOM + CRLF（PowerShell 5.1 对无 BOM 的 UTF-8 会按 ANSI 解析）
    - .cmd  -> GBK(cp936) + CRLF（cmd.exe 必须 CRLF，否则 rem 注释会被拆行执行）
    - 其它  -> UTF-8（无 BOM）+ CRLF
    """
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    ext = os.path.splitext(src)[1].lower()
    with open(src, "rb") as f:
        raw = f.read()
    text = decode_any(raw)
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\r\n")
    if ext == ".ps1":
        data = text.encode("utf-8-sig")
    elif ext in (".cmd", ".bat"):
        data = text.encode("cp936", errors="replace")
    else:
        data = text.encode("utf-8")
    with open(dst, "wb") as f:
        f.write(data)


def stage_bundle(stage):
    """解压即装：所有文件平铺在顶层之外的 scripts/，顶层放 README/install。"""
    copy(os.path.join(ROOT, "README.md"), os.path.join(stage, "README.md"))
    lic = os.path.join(ROOT, "LICENSE")
    if os.path.exists(lic):
        copy(lic, os.path.join(stage, "LICENSE"))
    for name in DOC_FILES:
        src = os.path.join(ROOT, "skill", name)
        if os.path.exists(src):
            copy(src, os.path.join(stage, "skill", name))
    for name in SCRIPT_FILES:
        src = os.path.join(ROOT, "scripts", name)
        if os.path.exists(src):
            copy(src, os.path.join(stage, "scripts", name))
    # 顶层再放一份安装入口，用户不用进子目录找
    for name in ("install.cmd", "install.ps1"):
        src = os.path.join(ROOT, "scripts", name)
        if os.path.exists(src):
            copy(src, os.path.join(stage, name))


def make_zip(stage, zpath):
    if os.path.exists(zpath):
        os.remove(zpath)
    total = 0
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for base, _dirs, files in os.walk(stage):
            for f in sorted(files):
                full = os.path.join(base, f)
                rel = os.path.relpath(full, stage).replace("\\", "/")
                z.write(full, rel)
                total += 1
    return total, os.path.getsize(zpath)


def main():
    log("=== vedio-concentrator 打包 v%s ===" % VERSION)
    for d in ("skill", "scripts"):
        if not os.path.isdir(os.path.join(ROOT, d)):
            log("!! 仓库结构不对，缺少 %s/ 目录" % d)
            return 1
    if not os.path.exists(os.path.join(ROOT, "README.md")):
        log("!! 缺少 README.md")
        return 1

    shutil.rmtree(DIST, ignore_errors=True)
    os.makedirs(DIST, exist_ok=True)

    # --- 仓库形态：src/<name>-<ver>/ = skill/ + scripts/ + 顶层文件
    src_stage = os.path.join(DIST, "src", "%s-%s" % (SKILL_NAME, VERSION))
    os.makedirs(src_stage, exist_ok=True)
    for name in ROOT_FILES + ["scripts", "skill"]:
        s = os.path.join(ROOT, name)
        if not os.path.exists(s):
            continue
        d = os.path.join(src_stage, name)
        if os.path.isdir(s):
            for base, _dirs, files in os.walk(s):
                for f in files:
                    if f.endswith((".pyc",)) or "__pycache__" in base:
                        continue
                    rel = os.path.relpath(os.path.join(base, f), s)
                    copy(os.path.join(base, f), os.path.join(d, rel))
        else:
            copy(s, d)
    n1, s1 = make_zip(src_stage, os.path.join(DIST, "%s-repo.zip" % SKILL_NAME))

    # --- 解压即装形态
    bstage = os.path.join(DIST, "bundle")
    os.makedirs(bstage, exist_ok=True)
    stage_bundle(bstage)
    n2, s2 = make_zip(bstage, os.path.join(DIST, "%s-bundle.zip" % SKILL_NAME))

    # --- 校验清单
    lines = []
    for zname in ("%s-repo.zip" % SKILL_NAME, "%s-bundle.zip" % SKILL_NAME):
        p = os.path.join(DIST, zname)
        lines.append("%s  %s" % (sha256(p), zname))
    sums = os.path.join(DIST, "SHA256SUMS.txt")
    with open(sums, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    log("")
    log("  %-34s %2d 文件  %6.1f KB" % ("%s-repo.zip" % SKILL_NAME, n1, s1 / 1024))
    log("  %-34s %2d 文件  %6.1f KB" % ("%s-bundle.zip" % SKILL_NAME, n2, s2 / 1024))
    log("  SHA256SUMS.txt")
    log("")
    log("  产物目录: %s" % DIST)
    return 0


if __name__ == "__main__":
    sys.exit(main())
