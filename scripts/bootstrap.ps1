# ============================================================
#  vedio-concentrator 一行安装（在线引导）
#
#  用法（PowerShell 里粘贴这一行）：
#    irm https://raw.githubusercontent.com/Edoardo-Zhang/vedio-concentrator/main/scripts/bootstrap.ps1 | iex
#
#  或者本地已解压时，直接双击 install.cmd 即可，不需要本脚本。
#
#  参数通过环境变量传：
#    $env:VC_DEST        skill 安装位置
#    $env:VC_SKIP_RUNTIME = 1   只装 skill，不下模型
#    $env:VC_REPO        GitHub 仓库，如 Edoardo-Zhang/vedio-concentrator
# ============================================================
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$repo = $env:VC_REPO
if (-not $repo) { $repo = "Edoardo-Zhang/vedio-concentrator" }
$ver = if ($env:VC_VERSION) { $env:VC_VERSION } else { "latest" }

Write-Host ""
Write-Host "vedio-concentrator 在线安装引导" -ForegroundColor Cyan
Write-Host "仓库: $repo   版本: $ver" -ForegroundColor DarkGray
Write-Host ""

# ---- 取 zip 地址 ----
$zipUrl = $null
if ($ver -eq "latest") {
    $api = "https://api.github.com/repos/$repo/releases/latest"
    try {
        $rel = Invoke-RestMethod -Uri $api -TimeoutSec 30 -Headers @{ "User-Agent" = "vc-bootstrap" }
        $asset = $rel.assets | Where-Object { $_.name -like "*bundle.zip" } | Select-Object -First 1
        if ($asset) { $zipUrl = $asset.browser_download_url }
    } catch {
        Write-Host "取 latest release 失败：$($_.Exception.Message)" -ForegroundColor Yellow
    }
} else {
    $zipUrl = "https://github.com/$repo/releases/download/$ver/vedio-concentrator-bundle.zip"
}
if (-not $zipUrl) {
    $zipUrl = "https://github.com/$repo/archive/refs/heads/main.zip"
    Write-Host "回退到源码包：$zipUrl" -ForegroundColor Yellow
}

# ---- 下载并解压到临时目录 ----
$tmp = Join-Path $env:TEMP ("vc_" + [guid]::NewGuid().ToString("N").Substring(0, 8))
New-Item -ItemType Directory -Force -Path $tmp | Out-Null
$zip = Join-Path $tmp "vc.zip"
Write-Host "下载中 ..." -ForegroundColor White
Invoke-WebRequest -Uri $zipUrl -OutFile $zip -UseBasicParsing -TimeoutSec 300
Expand-Archive -Path $zip -DestinationPath $tmp -Force
Write-Host "已解压到 $tmp" -ForegroundColor Green

# ---- 找到安装器并执行 ----
$installer = Get-ChildItem $tmp -Recurse -Filter "install.ps1" |
    Where-Object { $_.DirectoryName -notlike "*\skill\*" } |
    Select-Object -First 1
if (-not $installer) { throw "压缩包里找不到 install.ps1" }

$args = @("-ExecutionPolicy", "Bypass", "-File", $installer.FullName)
if ($env:VC_DEST) { $args += @("-Dest", $env:VC_DEST) }
if ($env:VC_SKIP_RUNTIME -eq "1") { $args += "-SkipRuntime" }

& powershell @args
$rc = $LASTEXITCODE
if ($rc -eq 0) {
    Write-Host ""
    Write-Host "装好了。在 Agent 里说「把这个视频做成脑图 <链接>」试试。" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "安装未完全成功（退出码 $rc）。临时目录保留在：$tmp" -ForegroundColor Yellow
}
