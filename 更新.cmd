@echo off
rem ============================================================
rem  更新.cmd — 双击这里完成一次更新
rem
rem  做四件事：检查分叉 -> 打包 zip -> 同步到本机 -> 提交推送到 GitHub
rem
rem  不想推送到 GitHub（只打包+同步本机），带上参数：
rem     powershell -ExecutionPolicy Bypass -File scripts\build_bundle.ps1 -NoPush
rem  也可以把本文件拖到 cmd 里执行：更新.cmd -NoPush
rem ============================================================
setlocal
chcp 936 >nul
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1

set PS1=%~dp0scripts\build_bundle.ps1
if not exist "%PS1%" (
  echo.
  echo [错误] 找不到 %PS1%
  echo        请确认本文件在仓库根目录，且 scripts\build_bundle.ps1 存在。
  echo.
  pause
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%" %*
set RC=%ERRORLEVEL%

echo.
if "%RC%"=="0" (
  echo [完成] 更新成功。
) else (
  echo [失败] 退出码 %RC% —— 看上面的 XX 行定位原因。
)
echo.
pause
exit /b %RC%
