param(
    [switch]$NoPush,     # 不跑 git，只打包+同步
    [switch]$NoCommit,   # 跑 git status 但跳过自动提交
    [string]$Message = "" # 提交说明，默认用时间戳
)

# ============================================================
#  build_bundle.ps1 — 一条命令完成"打包 -> 同步本机 -> 提交推送"
#
#  在仓库根目录执行：powershell -ExecutionPolicy Bypass -File scripts\build_bundle.ps1
#  或者直接双击仓库根目录的 更新.cmd
# ============================================================
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent $scriptDir
Set-Location $root

$script:fail = 0

function Step($n, $total, $text) {
    Write-Host ""
    Write-Host ("[" + $n + "/" + $total + "] " + $text) -ForegroundColor Cyan
}
function Ok($text)   { Write-Host ("      OK  " + $text) -ForegroundColor Green }
function Warn($text) { Write-Host ("      !!  " + $text) -ForegroundColor Yellow }
function Bad($text)  { Write-Host ("      XX  " + $text) -ForegroundColor Red; $script:fail = 1 }

Write-Host ""
Write-Host "==============================================" -ForegroundColor Cyan
Write-Host "  vedio-concentrator 更新" -ForegroundColor Cyan
Write-Host ("  仓库: " + $root) -ForegroundColor DarkGray
Write-Host "==============================================" -ForegroundColor Cyan

# ---------------------------------------------------------- 1. 有没有分叉
Step 1 4 "检查三份拷贝有没有分叉"
& python (Join-Path $scriptDir "check_sync.py")
if ($LASTEXITCODE -ne 0) {
    Warn "有分叉（见上）。打包会继续，但请先处理，否则可能发出旧代码。"
} else {
    Ok "没有分叉"
}

# ---------------------------------------------------------- 2. 打包
Step 2 4 "打包 zip"
& python (Join-Path $scriptDir "build_dist.py")
if ($LASTEXITCODE -ne 0) {
    Bad "打包失败，后面不做了"
    exit 1
}

$dist = Join-Path $root "dist"
$repo = Join-Path $dist "vedio-concentrator-repo.zip"
$bundle = Join-Path $dist "vedio-concentrator-bundle.zip"
foreach ($f in @($repo, $bundle)) {
    if (Test-Path $f) {
        $kb = [math]::Round((Get-Item $f).Length / 1KB, 1)
        Ok ((Split-Path $f -Leaf) + "  " + $kb + " KB")
    } else {
        Bad ("没生成 " + (Split-Path $f -Leaf))
    }
}
if ($script:fail -eq 1) { exit 1 }

# ---------------------------------------------------------- 3. 同步到本机
Step 3 4 "同步到你本机装的那份（这样你用的就是新版）"
& python (Join-Path $scriptDir "setup.py") --skill-only
if ($LASTEXITCODE -ne 0) {
    Bad "同步失败"
} else {
    Ok "已同步到 %USERPROFILE%\.cursor\skills\vedio-concentrator"
}

# ---------------------------------------------------------- 4. git
Step 4 4 "提交并推送"
if ($NoPush) {
    Warn "指定了 -NoPush，跳过"
} else {
    $null = & git rev-parse --is-inside-work-tree 2>&1
    if ($LASTEXITCODE -ne 0) {
        Bad "这不是 git 仓库"
    } else {
        $pending = & git status --porcelain
        if (-not $pending) {
            Ok "没有需要提交的改动"
        } elseif ($NoCommit) {
            Warn "有改动但指定了 -NoCommit，你自己去 GitHub Desktop 提交"
            $pending | ForEach-Object { Write-Host ("        " + $_) -ForegroundColor DarkGray }
        } else {
            if (-not $Message) {
                $Message = "更新 " + (Get-Date -Format "yyyy-MM-dd HH:mm")
            }
            & git add -A
            & git commit -m $Message | Out-Null
            if ($LASTEXITCODE -ne 0) {
                Bad "提交失败"
            } else {
                Ok ("已提交: " + $Message)
                Write-Host "      正在推送 ..." -ForegroundColor DarkGray
                # 推送重试。两个实测得到的必要设计：
                # 1) 用 Start-Process 而不是 & git：Invoke-Quiet 里的 `| Out-Null`
                #    会把 $LASTEXITCODE 重置掉，导致成功也被判成失败。
                # 2) 降级 HTTP/1.1：国内代理对 git 默认的 HTTP/2 常报
                #    "TLS connect error: unexpected eof while reading"。
                $pushed = $false
                $attempts = @(
                    @(),
                    @("-c", "http.version=HTTP/1.1"),
                    @("-c", "http.version=HTTP/1.1"),
                    @("-c", "http.version=HTTP/1.1", "-c", "http.postBuffer=524288000")
                )
                for ($k = 0; $k -lt $attempts.Count; $k++) {
                    if ($k -gt 0) {
                        Write-Host ("      第 " + ($k + 1) + " 次尝试...") -ForegroundColor DarkYellow
                        Start-Sleep -Seconds 3
                    }
                    $gitArgs = $attempts[$k] + @("push")
                    $gp = Start-Process -FilePath "git" -ArgumentList $gitArgs `
                        -NoNewWindow -Wait -PassThru
                    if ($gp.ExitCode -eq 0) { $pushed = $true; break }
                }
                if (-not $pushed) {
                    Bad "推送失败（网络）。手动重试：cd 到仓库执行 git push；仍失败则 git config http.version HTTP/1.1"
                } else {
                    Ok "已推送到 GitHub"
                }
            }
        }
    }
}

# ---------------------------------------------------------- 收尾
Write-Host ""
Write-Host "==============================================" -ForegroundColor Cyan
if ($script:fail -eq 0) {
    Write-Host "  全部完成" -ForegroundColor Green
} else {
    Write-Host "  有步骤失败，看上面的 XX 行" -ForegroundColor Yellow
}
Write-Host "==============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  想发新版给别人用，还要去网页传附件：" -ForegroundColor White
Write-Host "    https://github.com/Edoardo-Zhang/vedio-concentrator/releases/new" -ForegroundColor Cyan
Write-Host ("    附件选: " + $bundle) -ForegroundColor Gray
Write-Host ""
exit $script:fail
