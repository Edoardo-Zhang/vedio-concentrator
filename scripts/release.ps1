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

# 带重试的 GitHub API 调用。
# 为什么需要：到 GitHub 的连接经常偶发 TLS 握手失败（代理切换/网络抖动），
# 一次失败就中断发版体验很差。只重试网络类错误，4xx 业务错误直接抛。
function Invoke-Api {
    param(
        [string]$Method = "GET",
        [string]$Uri,
        [hashtable]$Headers,
        $Body = $null,           # byte[] 或 $null
        [string]$ContentType = "application/json; charset=utf-8",
        [int]$TimeoutSec = 60,
        [int]$Tries = 5
    )
    $lastErr = $null
    for ($i = 1; $i -le $Tries; $i++) {
        try {
            $params = @{
                Method      = $Method
                Uri         = $Uri
                Headers     = $Headers
                TimeoutSec  = $TimeoutSec
                ErrorAction = "Stop"
            }
            if ($null -ne $Body) {
                $params["Body"] = $Body
                $params["ContentType"] = $ContentType
            }
            return Invoke-RestMethod @params
        } catch {
            $lastErr = $_
            $status = 0
            try { $status = [int]$_.Exception.Response.StatusCode } catch { $status = 0 }
            if ($status -ge 400 -and $status -lt 500) { throw }   # 业务错误，重试无意义
            if ($i -lt $Tries) {
                $wait = 1.5 * $i
                Write-Host ("          （网络错误，第 " + $i + " 次重试，等 " + $wait + "s）") -ForegroundColor DarkYellow
                Start-Sleep -Milliseconds ([int]($wait * 1000))
            }
        }
    }
    throw $lastErr
}

# ---------------------------------------------------------- 版本号规范化
$Version = $Version.TrimStart("v", "V")
if ($Version -notmatch '^\d+\.\d+\.\d+$') {
    Die ("版本号格式不对: " + $Version + "（应形如 1.0.2）")
}

# 说明文件必须在这里就读进来！
# 原因：第 3 步的 build_dist.py 会清空整个 dist/ 目录。如果说明文件放在 dist/ 里
# （很自然的做法），到第 5 步再读就已经被删了，脚本会静默回退到"自动收集提交"，
# 于是发布出去的说明是错的。这个坑实际踩过一次。
$NotesFromFile = ""
if ($NotesFile) {
    if (-not (Test-Path $NotesFile)) {
        Die ("-NotesFile 指定的文件不存在: " + $NotesFile)
    }
    $NotesFromFile = [System.IO.File]::ReadAllText($NotesFile, [System.Text.Encoding]::UTF8)
    if (-not $NotesFromFile.Trim()) { Die ("-NotesFile 文件是空的: " + $NotesFile) }
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
$credRaw = ("protocol=https`nhost=github.com`n`n" | & git credential fill 2>$null | Out-String)
# 注意 .Trim()：Out-String 的行尾是 \r\n，正则会把 \r 一起捕获，
# 带 \r 的令牌发给 API 会得到莫名其妙的 401 或 404。
$Token = (($credRaw -split "`n" | Where-Object { $_ -match '^password=' }) -replace '^password=','').Trim()
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
    $null = Invoke-Api -Uri "$Api/git/ref/tags/$Tag" -Headers $Hdr -TimeoutSec 30
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
# 用 Start-Process 而不是调用运算符：子进程里的 git push 会往 stderr 写正常日志
# （"To https://..."、"branch ... set up to track"），而 PowerShell 5.1 把原生命令的
# stderr 当错误记录，配合 $ErrorActionPreference='Stop' 会在中途打断本脚本。
# Start-Process 让子进程完全独立，stderr 不会污染父进程，退出码用 ExitCode 取。
$proc = Start-Process -FilePath "powershell" `
    -ArgumentList "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$bb`"", "-Message", "`"$commitMsg`"" `
    -NoNewWindow -Wait -PassThru
if ($proc.ExitCode -ne 0) { Die ("build_bundle.ps1 失败（退出码 " + $proc.ExitCode + "），已中止") }
Ok "打包 / 同步 / 推送 完成"

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
    $null = Invoke-Api -Method Post -Uri "$Api/git/refs" -Headers $Hdr `
        -Body ([System.Text.Encoding]::UTF8.GetBytes($tagBody)) -TimeoutSec 60
    Ok "tag 已在 GitHub 创建"
} catch {
    Die ("建 tag 失败: " + $_.Exception.Message)
}

# ---------------------------------------------------------- 生成说明
Step 5 $TOTAL "生成版本说明"

if (-not $Notes) {
    if ($NotesFromFile) {
        $Notes = $NotesFromFile
        Ok ("使用 -NotesFile 的说明（" + $Notes.Length + " 字符）")
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
    $rel = Invoke-Api -Method Post -Uri "$Api/releases" -Headers $Hdr `
        -Body ([System.Text.Encoding]::UTF8.GetBytes($relBody)) -TimeoutSec 60
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
    # 附件走 Body 传 byte[]：Invoke-Api 内部重试时需要能重复提交，
    # 而 -InFile 只在单次调用里有效，重试会失败。
    $asset = Invoke-Api -Method Post -Uri ($uploadUrl + "?name=vedio-concentrator-bundle.zip") `
        -Headers $hUp -Body ([System.IO.File]::ReadAllBytes($bundle)) `
        -ContentType "application/zip" -TimeoutSec 600 -Tries 3
    Ok ("上传成功: " + $asset.name + "  " + $asset.size + " 字节")
} catch {
    Die ("上传附件失败: " + $_.Exception.Message)
}

# 关键校验：附件必须在，且字节数与本地一致
$verify = Invoke-Api -Uri "$Api/releases/$($rel.id)" -Headers $Hdr -TimeoutSec 60
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
