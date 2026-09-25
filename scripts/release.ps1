param(
    [Parameter(Mandatory = $true)]
    [string]$Version,             # 如 1.0.2（不带 v）

    [string]$Title = "",          # Release 标题，默认 "v<版本>"
    [string]$Notes = "",          # 版本说明，默认自动收集本次提交
    [string]$NotesFile = "",      # 从文件读说明（比 -Notes 方便写长文）
    [switch]$Draft,               # 建草稿而不直接发布
    [switch]$Prerelease,
    [switch]$SkipPush,            # 只打包不推送（本地试）
    [switch]$Yes,                 # 跳过确认
    [switch]$WhatIf               # 预演：只打印将做什么，不改任何东西
)

# ============================================================
#  发布.ps1 — 一条命令走完整个发版流程
#
#    改版本号 -> 打包 -> 提交推送 -> 建 tag -> 建 Release -> 传附件 -> 回填 SHA256 -> 校验
#
#  为什么要它：手动发版最容易漏的就是"上传附件"这一步，而 GitHub 不会提醒你，
#  Release 照样能发布出去。之前 v1.0.1 就这么漏过一次。
#
#  用法：
#    powershell -ExecutionPolicy Bypass -File scripts\发布.ps1 -Version 1.0.2
#    powershell -ExecutionPolicy Bypass -File scripts\发布.ps1 -Version 1.0.2 -NotesFile notes.md
#    powershell -ExecutionPolicy Bypass -File scripts\发布.ps1 -Version 1.0.2 -WhatIf   # 预演
# ============================================================

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent $scriptDir
Set-Location $root

$script:fail = 0

function Step($n, $total, $t) {
    Write-Host ""
    Write-Host ("[" + $n + "/" + $total + "] " + $t) -ForegroundColor Cyan
}
function Ok($t)   { Write-Host ("      OK  " + $t) -ForegroundColor Green }
function Info($t) { Write-Host ("          " + $t) -ForegroundColor DarkGray }
function Warn($t) { Write-Host ("      !!  " + $t) -ForegroundColor Yellow }
function Bad($t)  { Write-Host ("      XX  " + $t) -ForegroundColor Red; $script:fail = 1 }
function Die($t)  { Bad $t; Write-Host ""; exit 1 }

function Invoke-Quiet {
    param([scriptblock]$Block)
    & $Block 2>$null | Out-Null
}

# 需要"拿到输出"时用它（Invoke-Quiet 会把输出丢掉）。
# 原生命令（git）的 stderr 必须吞掉，否则 $ErrorActionPreference='Stop' 会中断脚本。
function Invoke-Capture {
    param([scriptblock]$Block)
    $out = & $Block 2>$null
    return ($out | Out-String).Trim()
}

# ---------------------------------------------------------- 版本号规范化
$Version = $Version.TrimStart("v", "V")
if ($Version -notmatch '^\d+\.\d+\.\d+$') {
    Die ("版本号格式不对: " + $Version + "（应形如 1.0.2）")
}
$Tag = "v" + $Version
if (-not $Title) { $Title = $Tag }

$TOTAL = 7
Write-Host ""
Write-Host "==============================================" -ForegroundColor Cyan
Write-Host ("  发布 " + $Tag) -ForegroundColor Cyan
if ($WhatIf) { Write-Host "  模式: 预演（不会改动任何东西）" -ForegroundColor Yellow }
Write-Host "==============================================" -ForegroundColor Cyan

# ---------------------------------------------------------- 前置检查
Step 1 $TOTAL "前置检查"

# 令牌
$credRaw = "protocol=https`nhost=github.com`n`n" | git credential fill 2>&1
$Token = ($credRaw | Select-String -Pattern '^password=') -replace '^password=',''
if (-not $Token) { Die "取不到 GitHub 凭据。先在 GitHub Desktop 里登录，或执行一次 git push 让它记住凭据。" }
$Hdr = @{ Authorization = "token $Token"; "User-Agent" = "vc-release" }

# 远程仓库
$remote = Invoke-Capture { git remote get-url origin }
$remote = $remote.Trim()
if ($remote -notmatch 'github\.com[:/]([^/]+)/([^/\s]+?)(\.git)?$') {
    Die ("无法从 origin 解析出 用户名/仓库名: " + $remote)
}
$Owner = $Matches[1]
$Repo = $Matches[2]
$RepoFull = "$Owner/$Repo"
$Api = "https://api.github.com/repos/$RepoFull"
Ok ("仓库: " + $RepoFull)

# 工作区
$dirty = Invoke-Capture { git status --porcelain }
if ($dirty.Trim()) {
    Warn "工作区有未提交的改动，会被一起提交："
    $dirty.Trim().Split("`n") | Select-Object -First 8 | ForEach-Object { Info $_.Trim() }
} else {
    Ok "工作区干净"
}

# tag 是否已存在
try {
    $null = Invoke-RestMethod -Uri "$Api/git/ref/tags/$Tag" -Headers $Hdr -TimeoutSec 30
    Die ("tag " + $Tag + " 在 GitHub 上已存在。换个版本号，或先去网页删掉它。")
} catch {
    if ($_.Exception.Response.StatusCode.value__ -eq 404) {
        Ok ("tag " + $Tag + " 可用")
    } else {
        Die ("查询 tag 失败: " + $_.Exception.Message)
    }
}

# ffmpeg 不是必须，但 build_dist 需要 python
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) { Die "找不到 python" }
Ok ("python: " + $py.Source)

if ($WhatIf) {
    Write-Host ""
    Write-Host "  预演结束。去掉 -WhatIf 即真正执行。" -ForegroundColor Yellow
    Write-Host ""
    exit 0
}

# ---------------------------------------------------------- 确认
if (-not $Yes) {
    Write-Host ""
    Write-Host ("  即将发布 " + $Tag + " 到 " + $RepoFull) -ForegroundColor White
    Write-Host "  这会：改版本号、打包、推送代码、建 tag、建 Release、传附件。" -ForegroundColor White
    $ans = Read-Host "  继续？(y/N)"
    if ($ans -notmatch '^[yY]') { Write-Host "  已取消"; exit 0 }
}

# ---------------------------------------------------------- 改版本号
Step 2 $TOTAL ("改版本号 -> " + $Version)
$bdPath = Join-Path $scriptDir "build_dist.py"
if (-not (Test-Path $bdPath)) { Die "找不到 build_dist.py" }
$bdText = [System.IO.File]::ReadAllText($bdPath, [System.Text.Encoding]::UTF8)
$bdNew = [regex]::Replace($bdText, '(?m)^VERSION\s*=\s*"[^"]*"', ('VERSION = "' + $Version + '"'))
if ($bdNew -eq $bdText) {
    Warn "版本号没变化（本来就是 $Version）"
} else {
    [System.IO.File]::WriteAllText($bdPath, $bdNew, (New-Object System.Text.UTF8Encoding($false)))
    Ok ("build_dist.py: VERSION = `"$Version`"")
}

# ---------------------------------------------------------- 打包 + 同步 + 推送
Step 3 $TOTAL "打包 / 同步本机 / 推送代码"
$bb = Join-Path $scriptDir "build_bundle.ps1"
if (-not (Test-Path $bb)) { Die "找不到 build_bundle.ps1" }
$commitMsg = "发布 " + $Tag + "：" + $Title
Invoke-Quiet { & powershell -NoProfile -ExecutionPolicy Bypass -File $bb -Message $commitMsg }
if ($LASTEXITCODE -ne 0) { Die "build_bundle.ps1 失败，已中止" }

$bundle = Join-Path $root "dist\vedio-concentrator-bundle.zip"
if (-not (Test-Path $bundle)) { Die ("没生成 " + $bundle) }
$bundleBytes = (Get-Item $bundle).Length
$bundleSha = (Get-FileHash $bundle -Algorithm SHA256).Hash.ToLower()
Ok ("bundle: " + $bundleBytes + " 字节")
Info ("SHA256: " + $bundleSha)

if ($SkipPush) {
    Warn "指定了 -SkipPush，后面建 tag / Release 需要代码已在远程，已中止"
    exit 0
}

# ---------------------------------------------------------- 建 tag
Step 4 $TOTAL ("建 tag " + $Tag)
# 用本地 HEAD 的 sha，确保 tag 指向刚提交的那次
$headSha = Invoke-Capture { git rev-parse HEAD }
if ($headSha -notmatch '^[0-9a-f]{40}$') { Die ("拿不到 HEAD sha: " + $headSha) }
# 本地也打一个，方便日后查
Invoke-Quiet { git tag -f $Tag $headSha }
Info ("HEAD = " + $headSha.Substring(0, 12))

$tagBody = @{ ref = "refs/tags/$Tag"; sha = $headSha } | ConvertTo-Json -Compress
try {
    $null = Invoke-RestMethod -Method Post -Uri "$Api/git/refs" -Headers $Hdr `
        -Body ([System.Text.Encoding]::UTF8.GetBytes($tagBody)) `
        -ContentType "application/json; charset=utf-8" -TimeoutSec 60
    Ok "tag 已在 GitHub 创建"
} catch {
    Die ("建 tag 失败: " + $_.Exception.Message)
}

# ---------------------------------------------------------- 生成说明
Step 5 $TOTAL "生成版本说明"

if (-not $Notes) {
    if ($NotesFile -and (Test-Path $NotesFile)) {
        $Notes = [System.IO.File]::ReadAllText($NotesFile, [System.Text.Encoding]::UTF8)
        Ok ("从 " + $NotesFile + " 读取说明（" + $Notes.Length + " 字符）")
    } else {
        # 自动收集上一个 tag 以来的提交
        $prevTag = Invoke-Capture { git describe --tags --abbrev=0 "$Tag^" }
        if ($prevTag) {
            $logLines = Invoke-Capture { git log --oneline --no-merges ("$prevTag..HEAD") }
            $Notes = "## 本次更新`n`n" + (($logLines.Trim().Split("`n") | ForEach-Object { "- " + $_.Trim() }) -join "`n")
            Ok ("自动收集 " + $prevTag + " 以来的提交")
        } else {
            $Notes = "## 本次更新`n`n- 见提交历史"
            Warn "没找到上一个 tag，用默认说明"
        }
        Info "想自定义请用 -Notes 或 -NotesFile"
    }
}

$NotesFull = @"

---

## 安装

下载下面的 ``vedio-concentrator-bundle.zip``，解压，双击 ``install.cmd``。
需要 Python 3.9+；首次安装会下载约 1.5 GB 语音模型。

一行安装（PowerShell）：

``````powershell
`$env:VC_REPO = "$RepoFull"
irm https://raw.githubusercontent.com/$RepoFull/main/scripts/bootstrap.ps1 | iex
``````

## 校验

``````
SHA256  $bundleSha
``````

⚠️ 下载的视频仅供个人学习使用，请遵守各平台服务条款。
"@
$NotesFull = $Notes.TrimEnd() + "`n" + $NotesFull

# ---------------------------------------------------------- 建 Release
Step 6 $TOTAL ("建 Release" + $(if ($Draft) { "（草稿）" } else { "" }))
$relBody = @{
    tag_name   = $Tag
    name       = $Title
    body       = $NotesFull
    draft      = [bool]$Draft
    prerelease = [bool]$Prerelease
} | ConvertTo-Json -Depth 5

try {
    $rel = Invoke-RestMethod -Method Post -Uri "$Api/releases" -Headers $Hdr `
        -Body ([System.Text.Encoding]::UTF8.GetBytes($relBody)) `
        -ContentType "application/json; charset=utf-8" -TimeoutSec 60
    Ok ("Release 已创建，id = " + $rel.id)
} catch {
    Die ("建 Release 失败: " + $_.Exception.Message)
}

# ---------------------------------------------------------- 传附件 + 校验
Step 7 $TOTAL "上传附件并校验"
$uploadUrl = $rel.upload_url -replace '\{\?name,label\}',''
$hUp = $Hdr.Clone()
$hUp["Content-Type"] = "application/zip"
try {
    $asset = Invoke-RestMethod -Method Post -Uri ($uploadUrl + "?name=vedio-concentrator-bundle.zip") `
        -Headers $hUp -InFile $bundle -TimeoutSec 600
    Ok ("上传成功: " + $asset.name + "  " + $asset.size + " 字节")
} catch {
    Die ("上传附件失败: " + $_.Exception.Message)
}

# 关键校验：附件必须在，且字节数与本地一致
$verify = Invoke-RestMethod -Uri "$Api/releases/$($rel.id)" -Headers $Hdr -TimeoutSec 60
$assets = @($verify.assets)
if ($assets.Count -eq 0) {
    Bad "Release 里没有附件！"
} elseif ($assets.Count -lt 1) {
    Bad "附件数量异常"
} else {
    $a = $assets | Where-Object { $_.name -eq "vedio-concentrator-bundle.zip" }
    if (-not $a) {
        Bad "找不到 vedio-concentrator-bundle.zip"
    } elseif ($a.size -ne $bundleBytes) {
        Bad ("附件大小不符: 远程 " + $a.size + " vs 本地 " + $bundleBytes)
    } else {
        Ok ("附件已确认: " + $a.size + " 字节（与本地一致）")
    }
}
# 说明里的 SHA256 是否等于实际
if ($verify.body -notmatch [regex]::Escape($bundleSha)) {
    Bad "说明里的 SHA256 与实际不符"
} else {
    Ok "说明里的 SHA256 已写入且正确"
}

# ---------------------------------------------------------- 收尾
Write-Host ""
Write-Host "==============================================" -ForegroundColor Cyan
if ($script:fail -eq 0) {
    Write-Host ("  " + $Tag + " 发布完成") -ForegroundColor Green
} else {
    Write-Host "  发布完成，但有校验未通过（见上面的 XX）" -ForegroundColor Yellow
}
Write-Host "==============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host ("  Release: " + $verify.html_url) -ForegroundColor Cyan
Write-Host ("  附件   : " + $bundleBytes + " 字节") -ForegroundColor Gray
Write-Host ("  SHA256 : " + $bundleSha) -ForegroundColor Gray
Write-Host ""
if ($Draft) {
    Write-Host "  这是草稿，需要去网页点 Publish release 才会公开。" -ForegroundColor Yellow
    Write-Host ""
}
exit $script:fail
