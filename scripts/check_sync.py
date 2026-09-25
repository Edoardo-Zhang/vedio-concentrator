# -*- coding: utf-8 -*-
"""check_sync.py — 护栏：检查三份拷贝有没有分叉，防止"改了一处忘了同步"。

为什么要它：
  本机同时存在三份 vedio-concentrator：
    1. 打包源   D:\\X Files\\DSH\\dsh01\\vedio-concentrator
    2. Git 仓库 D:\\X Files\\DSH\\dsh01\\gh-publish
    3. 已安装   %USERPROFILE%\\.cursor\\skills\\vedio-concentrator   ← Agent 实际跑的那份
  改了其中一份而忘了另外两份，就会出现"GitHub 上是新版、你自己机器上还是旧版"
  或者"发 Release 时传的是旧 zip"。

比对规则（只看内容，不看格式）：
  - 忽略 BOM、换行（CRLF/LF）、编码（.cmd 是 GBK，其余 UTF-8）
  - 忽略 .git / __pycache__ / dist / _test / *.pyc / *.log
  - 只比对"哪些文件应该三边一致"，各目录特有的文件（如 dist/）不参与

用法:
  python check_sync.py              # 检查并打印报告；有分叉返回 1
  python check_sync.py --quiet      # 只在有分叉时输出
  python check_sync.py --json       # 机器可读
  python check_sync.py --show-copy  # 额外打印"从 Git仓库 同步到 打包源"的命令
"""
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)          # gh-publish（Git 仓库）
WORKDIR = os.path.dirname(ROOT)       # D:\X Files\DSH\dsh01


def resolve_src():
    """定位"打包源"那份拷贝。

    优先读环境变量 VEDIO_CONCENTRATOR_SRC；否则在工作区里找同名目录；
    找不到就返回 None（不算错误，只跳过比对）。
    """
    env = os.environ.get("VEDIO_CONCENTRATOR_SRC")
    if env and os.path.isdir(env):
        return env
    for cand in (os.path.join(WORKDIR, "vedio-concentrator"),
                 os.path.join(WORKDIR, "vedio_concentrator")):
        if os.path.isdir(cand) and os.path.abspath(cand) != os.path.abspath(ROOT):
            return cand
    return None


# 三份拷贝：展示名、路径、必需性（非必需的不存在时只跳过，不算错）
SOURCES = [
    ("打包源", resolve_src(), False),
    ("Git仓库", ROOT, True),
    ("已安装", os.path.join(os.path.expanduser("~"), ".cursor", "skills",
                            "vedio-concentrator"), False),
]

# 应该逐字节对等的两份拷贝（镜像关系）
PAIR = ["Git仓库", "打包源"]

# 仓库里应当存在的全部文件（相对仓库根）。新加了文件记得同步加到这里。
PAIR_FILES = [
    "README.md", "LICENSE", ".gitignore", "GITHUB-GUIDE.md", "维护必读.md",
    "更新.cmd",
    "skill/SKILL.md", "skill/reference.md",
    "scripts/v2mm.py", "scripts/vcproxy.py", "scripts/render_mindmap.py",
    "scripts/setup_check.py", "scripts/install_runtime.py", "scripts/setup.py",
    "scripts/install.cmd", "scripts/install.ps1", "scripts/bootstrap.ps1",
    "scripts/build_dist.py", "scripts/build_bundle.ps1", "scripts/check_sync.py",
    "scripts/make_gif.ps1", "scripts/release.ps1",
    "docs/demo-outline.md", "docs/mindmap-preview.gif",
]

# 「已安装」那份是子集：只包含真正要跑的脚本和 skill 文档。
# 名单之外的文件（README/LICENCE/打包脚本）装过去反而是垃圾。
RUNTIME_SET = {
    "skill/SKILL.md", "skill/reference.md",
    "scripts/v2mm.py", "scripts/vcproxy.py", "scripts/render_mindmap.py",
    "scripts/setup_check.py", "scripts/install_runtime.py", "scripts/setup.py",
    "scripts/install.cmd", "scripts/install.ps1",
}


def decode_any(raw):
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig")
    for enc in ("utf-8", "cp936"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def content_hash(path):
    """内容指纹：忽略 BOM、换行、编码差异。"""
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError:
        return None
    text = decode_any(raw)
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip("\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def locate(name, root, is_install):
    """在某个拷贝里找到某个逻辑文件的真实路径。"""
    cands = [os.path.join(root, name)]
    if is_install:
        # 已安装形态：文档在根，脚本在 scripts/
        cands.append(os.path.join(root, os.path.basename(name)))
        cands.append(os.path.join(root, "scripts", os.path.basename(name)))
    else:
        cands.append(os.path.join(root, "scripts", os.path.basename(name)))
        cands.append(os.path.join(root, "skill", os.path.basename(name)))
    for c in cands:
        if os.path.isfile(c):
            return c
    return None


# 需要参与比对的全部文件（镜像对 + 运行时子集 的并集）
COMPARE = sorted(set(PAIR_FILES) | RUNTIME_SET)


def scan():
    report = {}
    for label, root, required in SOURCES:
        if not root or not os.path.isdir(root):
            report[label] = {"root": root, "exists": False, "required": required, "files": {}}
            continue
        is_install = label == "已安装"
        files = {}
        for name in COMPARE:
            p = locate(name, root, is_install)
            files[name] = content_hash(p) if p else None
        report[label] = {"root": root, "exists": True, "required": required, "files": files}
    return report


def main():
    quiet = "--quiet" in sys.argv
    as_json = "--json" in sys.argv
    rep = scan()

    present = [(k, v) for k, v in rep.items() if v["exists"]]
    labels = [k for k, _ in present]

    drift_value = []    # 镜像对里同一个文件内容不一样
    drift_missing = []  # 镜像对里有的拷贝缺文件

    # 1) 镜像对（Git仓库 vs 打包源）：必须完全一致，一个文件都不能少
    pair = [l for l in PAIR if l in labels]
    if len(pair) == 2:
        for name in PAIR_FILES:
            a, b = pair
            ha, hb = rep[a]["files"].get(name), rep[b]["files"].get(name)
            if ha and hb:
                if ha != hb:
                    drift_value.append((name, {ha: [a], hb: [b]}))
            elif ha or hb:
                missing = [l for l in pair if not rep[l]["files"].get(name)]
                drift_missing.append((name, missing))

    # 2) 已安装那份：只检查"该有的在不在、内容对不对"
    if "已安装" in labels and len(pair) >= 1:
        base = pair[0] if pair else None
        for name in sorted(RUNTIME_SET):
            h_ins = rep["已安装"]["files"].get(name)
            h_ref = rep[base]["files"].get(name) if base else None
            if h_ref and not h_ins:
                drift_missing.append((name, ["已安装"]))
            elif h_ref and h_ins and h_ins != h_ref:
                drift_value.append((name, {h_ref: [base], h_ins: ["已安装"]}))

    missing_required = [k for k, v in rep.items() if v["required"] and not v["exists"]]
    problems = drift_value + drift_missing

    if as_json:
        print(json.dumps({
            "report": rep,
            "drift_value": [p[0] for p in drift_value],
            "drift_missing": {n: m for n, m in drift_missing},
            "missing_required": missing_required,
        }, ensure_ascii=False, indent=2))
        return 1 if problems or missing_required else 0

    if not quiet:
        print("=== 三份拷贝同步检查 ===")
        for label, info in rep.items():
            if info["exists"]:
                n = len([1 for h in info["files"].values() if h])
                print("  [有] %-8s %d 个文件  %s" % (label, n, info["root"]))
            else:
                mark = "!!" if info["required"] else "--"
                print("  [%s] %-8s 不存在        %s" % (mark, label, info["root"]))
        print("")

    if missing_required:
        print("!! 找不到必需的拷贝: %s" % ", ".join(missing_required))
        return 1

    if not problems:
        if not quiet:
            print("  ✓ 三份拷贝内容一致，没有分叉")
        return 0

    print("!! 检测到分叉:")
    if drift_value:
        print("   内容不一致：")
        for name, vals in drift_value:
            print("      %s" % name)
            for _h, ls in vals.items():
                print("         这些拷贝是同一版: %s" % " / ".join(ls))
    if drift_missing:
        print("   有的拷贝缺这个文件：")
        for name, missing in drift_missing:
            print("      %-30s 缺失: %s" % (name, " / ".join(missing)))

    if "--show-copy" in sys.argv:
        print("")
        print("  从「Git仓库」同步到「打包源」的复制命令：")
        src_root = rep["Git仓库"]["root"]
        dst_root = rep.get("打包源", {}).get("root")
        if not dst_root:
            print("      （没有找到打包源，跳过）")
        else:
            todo = [n for n, _ in drift_value]
            todo += [n for n, m in drift_missing if "打包源" in m]
            for n in todo:
                s = locate(n, src_root, False)
                if not s:
                    continue
                d = os.path.join(dst_root, n.replace("/", os.sep))
                print("      copy \"%s\" \"%s\"" % (s, d))
            if not todo:
                print("      （没有需要复制的）")
    print("")
    print("  怎么修：先定唯一源（推荐 Git仓库），再同步过去：")
    print("     cd \"%s\"" % ROOT)
    print("     python scripts\\setup.py --skill-only            # 同步到「已安装」")
    print("     python scripts\\check_sync.py --show-copy        # 打印复制命令")
    print("  或者干脆删掉多余的那份拷贝。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
