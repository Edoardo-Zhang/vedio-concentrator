# vedio-concentrator 安装脚本（Windows，PowerShell 5.1 及以上）
# 被 install.cmd 调用，也可单独运行：
#   powershell -ExecutionPolicy Bypass -File install.ps1
# 参数：
#   -Dest <目录>         skill 安装位置，默认 ~\.cursor\skills\vedio-concentrator
#   -SkipRuntime         只装 skill，不下载模型/ffmpeg（约 1.6 GB）
#   -Proxy <url>         运行时下载走代理，默认自动按源测速
#   -Repo <user/repo>    从 GitHub Release 取包时用（install.cmd 远程模式）
param(
    [string]$Dest = "$env:USERPROFILE\.cursor\skills\vedio-concentrator",
    [switch]$SkipRuntime,
    [string]$Proxy = "",
    [string]$Repo = ""
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

function Say($msg, $color = "Gray") {
    Write-Host $msg -ForegroundColor $color
}
function Fail($msg) {
    Say ""
    Say "[错误] $msg" "Red"
    Say "        把上面的输出发给我，或见 README 的「排错」一节。" "DarkGray"
    exit 1
}

Say ""
Say "==============================================" "Cyan"
Say "  vedio-concentrator 安装程序" "Cyan"
Say "  视频下载 + 字幕/转写 + 交互式脑图" "Cyan"
Say "==============================================" "Cyan"
Say ""

# ---------------------------------------------------------- 1. 检查 Python
Say "[1/5] 检查 Python ..." "White"
$py = $null
foreach ($cand in @("python", "py")) {
    $c = Get-Command $cand -ErrorAction SilentlyContinue
    if ($c) {
        & $c.Source -c "import sys; sys.exit(0 if sys.version_info >= (3,9) else 1)" 2>$null
        if ($LASTEXITCODE -eq 0) { $py = $c.Source; break }
    }
}
if (-not $py) {
    Fail "需要 Python 3.9+。请从 https://www.python.org/downloads/ 安装，并勾选 Add to PATH。"
}
$pyver = (& $py --version 2>&1) -join " "
Say "      OK  $pyver  ($py)" "Green"

# ---------------------------------------------------------- 2. 定位源文件
Say "[2/5] 定位安装源 ..." "White"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$cands = @(
    (Join-Path $here "setup.py"),                              # 已安装形态：同目录
    (Join-Path $here "scripts\setup.py"),                      # bundle 形态：本文件在顶层
    (Join-Path (Split-Path -Parent $here) "scripts\setup.py")  # 仓库形态：本文件在 scripts\ 里
)
$scriptSrc = $cands | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $scriptSrc) {
    $tried = $cands -join [Environment]::NewLine + '        '
    Fail ("找不到 setup.py。已找过：`n        " + $tried + "`n        请确认 zip 已完整解压。")
}
Say "      OK  安装脚本: $scriptSrc" "Green"

# ---------------------------------------------------------- 3. 装 skill
Say "[3/5] 安装 skill 到 $Dest ..." "White"
# 关键：把工作目录切到临时目录。否则 cmd.exe 可能正持有解压目录的句柄，
# 复制文件时会报 WinError 32（文件被占用），尤其在刚解压完被杀软扫描时。
$origCwd = Get-Location
try {
    Set-Location $env:TEMP
    & $py $scriptSrc --skill-only --dest $Dest
    $copyRc = $LASTEXITCODE
} finally {
    Set-Location $origCwd
}
if ($copyRc -ne 0) { Fail "复制 skill 文件失败。" }
Say "      OK" "Green"

# ---------------------------------------------------------- 4. 装运行时
if ($SkipRuntime) {
    Say "[4/5] 跳过运行时装（-SkipRuntime）" "Yellow"
    Say "      之后想补装：python `"$Dest\setup.py`" --runtime-only" "DarkGray"
} else {
    Say "[4/5] 安装运行时（模型约 1.5 GB，首次较慢）..." "White"
    Say "      正在测速选源；直连慢会自动走 hf-mirror / 代理" "DarkGray"
    if ($Proxy) { $env:VEDIO_CONCENTRATOR_PROXY = $Proxy }
    & $py $scriptSrc --runtime-only
    if ($LASTEXITCODE -ne 0) {
        Say ""
        Say "      运行时装没装全（可能是网络问题）。" "Yellow"
        Say "      skill 已经能用，网络恢复后重跑本脚本即可续传。" "Yellow"
    } else {
        Say "      OK" "Green"
    }
}

# ---------------------------------------------------------- 5. 自检
Say "[5/5] 自检 ..." "White"
& $py (Join-Path $Dest "scripts\setup_check.py")
$checkRc = $LASTEXITCODE
Say ""

# ---------------------------------------------------------- 完成
Say "==============================================" "Cyan"
if ($checkRc -eq 0) {
    Say "  安装完成" "Green"
} else {
    Say "  安装完成，但自检有未通过项（见上）" "Yellow"
}
Say "==============================================" "Cyan"
Say ""
Say "skill 位置: $Dest"
Say ""
Say "怎么用：在 Codex / DSH 里直接说：" "White"
Say "    「把这个视频做成脑图 https://...」" "Cyan"
Say ""
Say "命令行用法：" "White"
Say "    python `"$Dest\scripts\v2mm.py`" `<URL>` --outdir .\out" "Gray"
Say "    python `"$Dest\scripts\render_mindmap.py`" --md .\out\outline.md --out .\out\mindmap.html" "Gray"
Say ""
Say "注意：下载的视频仅供个人学习使用，请遵守各平台条款。" "DarkGray"
Say ""
exit $checkRc
