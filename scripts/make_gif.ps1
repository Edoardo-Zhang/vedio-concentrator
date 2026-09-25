param(
    [string]$Html   = "docs\demo-mindmap.html",   # 已渲染的脑图 HTML（相对仓库根）
    [string]$Out    = "docs\mindmap-preview.gif", # 输出 GIF（相对仓库根）
    [int]$Port      = 8099,
    [int]$Width     = 1200,
    [int]$Height    = 675,
    [int]$HoldMs    = 900,    # 每帧停留
    [int]$LastHoldMs = 2200,  # 最后一帧多停一会儿
    [int]$Fps       = 6,
    [switch]$KeepFrames
)

# ============================================================
#  make_gif.ps1 — 把脑图的"逐层展开"过程做成演示 GIF
#
#  原理：
#    1) 起一个本地 HTTP 服务（无头截图走 file:// 不稳定）
#    2) 用 ?static=1&expand=N 抓每一层展开状态，得到一堆 PNG 帧
#    3) 用 ffmpeg 调色板法合成 GIF（Pillow 也行，但没 ffmpeg 清晰）
#
#  用法（在仓库根目录执行）：
#    powershell -ExecutionPolicy Bypass -File scripts\make_gif.ps1
# ============================================================
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent $scriptDir
Set-Location $root

function Ok($t)   { Write-Host ("  OK  " + $t) -ForegroundColor Green }
function Info($t) { Write-Host ("      " + $t) -ForegroundColor DarkGray }
function Bad($t)  { Write-Host ("  XX  " + $t) -ForegroundColor Red }

# 统一的"跑外部命令并吞掉 stderr"封装。
# 为什么需要：Edge 和 ffmpeg 都会往 stderr 写正常日志（"N bytes written"、进度等），
# 而 PowerShell 5.1 把原生命令的 stderr 当错误记录，配合 $ErrorActionPreference='Stop'
# 会直接中断脚本。必须在 script block 内用 2>$null。
function Invoke-Quiet {
    param([scriptblock]$Block)
    & $Block 2>$null | Out-Null
}

# ---------------------------------------------------------- 找工具
$ffmpeg = Join-Path $env:LOCALAPPDATA "vedio-concentrator\bin\ffmpeg.exe"
if (-not (Test-Path $ffmpeg)) {
    $c = Get-Command ffmpeg -ErrorAction SilentlyContinue
    if ($c) { $ffmpeg = $c.Source }
}
if (-not (Test-Path $ffmpeg)) {
    Bad "找不到 ffmpeg。先运行 python scripts\setup.py --runtime-only 安装。"
    exit 1
}

$edge = @(
    "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe",
    "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe",
    "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
    "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $edge) { Bad "找不到 Edge 或 Chrome"; exit 1 }

$htmlPath = Join-Path $root $Html
if (-not (Test-Path $htmlPath)) {
    Bad ("找不到 " + $htmlPath + "，先跑 render_mindmap.py")
    exit 1
}

Write-Host ""
Write-Host "==============================================" -ForegroundColor Cyan
Write-Host "  生成演示 GIF" -ForegroundColor Cyan
Write-Host ("  源文件: " + $Html) -ForegroundColor DarkGray
Write-Host "==============================================" -ForegroundColor Cyan
Write-Host ""
Info ("ffmpeg : " + $ffmpeg)
Info ("浏览器 : " + $edge)

# ---------------------------------------------------------- 起本地服务
$htmlDir = Split-Path -Parent $htmlPath
$htmlName = Split-Path -Leaf $htmlPath
$srv = Start-Process -FilePath "python" `
    -ArgumentList "-m", "http.server", $Port, "--bind", "127.0.0.1", "--directory", "`"$htmlDir`"" `
    -PassThru -WindowStyle Hidden
Start-Sleep -Seconds 2
try {
    $probe = Invoke-WebRequest -Uri ("http://127.0.0.1:" + $Port + "/" + $htmlName) -UseBasicParsing -TimeoutSec 10
    if ($probe.StatusCode -ne 200) { throw ("HTTP " + $probe.StatusCode) }
    Ok ("本地服务已启动，端口 " + $Port)
} catch {
    Bad ("本地服务没起来: " + $_.Exception.Message)
    if ($srv -and -not $srv.HasExited) { $srv.Kill() }
    exit 1
}

# ---------------------------------------------------------- 抓帧
$framesDir = Join-Path $root "docs\_gif_frames"
if (Test-Path $framesDir) { Remove-Item $framesDir -Recurse -Force }
New-Item -ItemType Directory -Force -Path $framesDir | Out-Null

# 每一层展开状态。数值 = 展开深度，-1 = 全部展开。
# 注意：本演示大纲只有 4 层，所以 -1 和 4 的画面完全相同——不要两个都放，
# 会出现一帧内容重复、GIF 白白变长。层数不同时按实际深度调整这个数组。
$levels = @(1, 2, 3, -1)
Write-Host ""
Write-Host ("[1/2] 抓 " + $levels.Count + " 帧") -ForegroundColor Cyan

$i = 0
foreach ($lv in $levels) {
    $i++
    $png = Join-Path $framesDir ("f{0:d2}.png" -f $i)
    $url = "http://127.0.0.1:$Port/$htmlName`?static=1&expand=$lv"
    Invoke-Quiet {
        & $edge --headless=new --disable-gpu --no-sandbox --hide-scrollbars `
            "--window-size=$Width,$Height" --virtual-time-budget=8000 `
            "--screenshot=$png" $url
    }
    # Edge 写文件是异步的：命令返回后文件可能还没落盘，必须轮询等待再校验。
    # 之前只 sleep 400ms，导致校验误报"抓帧失败"（其实帧是好的）。
    $waited = 0
    while (-not (Test-Path $png) -and $waited -lt 8000) {
        Start-Sleep -Milliseconds 200
        $waited += 200
    }
    if (Test-Path $png) {
        $kb = [math]::Round((Get-Item $png).Length / 1KB, 1)
        if ($kb -lt 5) {
            Bad ("expand=$lv 只有 " + $kb + " KB，疑似空白帧")
        } else {
            Ok ("expand=$lv  ->  " + $kb + " KB")
        }
    } else {
        Bad ("expand=$lv 等待 " + $waited + "ms 后仍无文件")
    }
}

$frames = Get-ChildItem $framesDir -Filter "*.png" | Sort-Object Name
if ($frames.Count -lt 2) {
    Bad "帧数不足，无法合成"
    if ($srv -and -not $srv.HasExited) { $srv.Kill() }
    exit 1
}

# ---------------------------------------------------------- 合成 GIF
Write-Host ""
Write-Host "[2/2] 合成 GIF（ffmpeg 调色板法）" -ForegroundColor Cyan

$outPath = Join-Path $root $Out
$outDir = Split-Path -Parent $outPath
if (-not (Test-Path $outDir)) { New-Item -ItemType Directory -Force -Path $outDir | Out-Null }

# 每帧持续时长：用 concat + duration 精确控制，比 -r 更能控制停留
$listFile = Join-Path $framesDir "list.txt"
$lines = @()
for ($n = 0; $n -lt $frames.Count; $n++) {
    $dur = if ($n -eq $frames.Count - 1) { $LastHoldMs } else { $HoldMs }
    $p = $frames[$n].FullName.Replace("\", "/")
    $lines += ("file '" + $p + "'")
    $lines += ("duration " + ([math]::Round($dur / 1000.0, 3)))
}
# concat 要求最后一张图重复一次，否则最后一帧时长会被忽略
$lines += ("file '" + $frames[$frames.Count - 1].FullName.Replace("\", "/") + "'")
Set-Content -Path $listFile -Value $lines -Encoding ASCII

$palette = Join-Path $framesDir "palette.png"
Invoke-Quiet {
    & $ffmpeg -y -loglevel error -f concat -safe 0 -i $listFile `
        -vf "fps=$Fps,scale=${Width}:-1:flags=lanczos,palettegen=stats_mode=diff" $palette
}
if (-not (Test-Path $palette)) { Bad "调色板生成失败"; if (-not $srv.HasExited) { $srv.Kill() }; exit 1 }

Invoke-Quiet {
    & $ffmpeg -y -loglevel error -f concat -safe 0 -i $listFile -i $palette `
        -lavfi "fps=$Fps,scale=${Width}:-1:flags=lanczos[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=3:diff_mode=rectangle" `
        -loop 0 $outPath
}

if ($srv -and -not $srv.HasExited) { $srv.Kill() }

if (-not (Test-Path $outPath)) { Bad "GIF 合成失败"; exit 1 }

$outKb = [math]::Round((Get-Item $outPath).Length / 1KB, 1)
Write-Host ""
Write-Host "==============================================" -ForegroundColor Cyan
Ok ("GIF: " + $outPath)
Ok ("大小: " + $outKb + " KB   帧数: " + $frames.Count + "   尺寸: " + $Width + "x" + $Height)
Write-Host "==============================================" -ForegroundColor Cyan
if ($outKb -gt 4000) {
    Write-Host ""
    Write-Host ("  提示：超过 4 MB 了，加载会慢。可以调小 -Width、-HoldMs，或减少帧数。") -ForegroundColor Yellow
}
Write-Host ""

if (-not $KeepFrames) {
    Remove-Item $framesDir -Recurse -Force -ErrorAction SilentlyContinue
    Info "已清理帧文件（加 -KeepFrames 可保留）"
}
