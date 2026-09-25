@echo off
rem ============================================================
rem  vedio-concentrator 一键安装（Windows 10/11）
rem  用法：双击本文件，或在 cmd 里执行 install.cmd
rem  可选参数：install.cmd -Dest "D:\my\skills" -SkipRuntime
rem
rem  本文件建议保存为 ANSI/GBK 编码。若中文显示为乱码，
rem  在下面 chcp 处把 936 改成 65001，并把本文件转存为 UTF-8。
rem ============================================================
setlocal
chcp 936 >nul
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1

rem ---- 找一个可用的 Python（3.9+）----
set PY=
for %%C in (python.exe py.exe) do (
  if not defined PY (
    where %%C >nul 2>nul && set PY=%%C
  )
)
if not defined PY (
  echo.
  echo [错误] 没找到 Python。
  echo        请先安装 Python 3.9 或更高版本：https://www.python.org/downloads/
  echo        安装时务必勾选 "Add python.exe to PATH"。
  echo.
  pause
  exit /b 1
)

rem py.exe 是启动器，需要显式指定版本
if /i "%PY%"=="py.exe" (
  py -3 --version >nul 2>nul && set PY=py -3
)

echo 使用 Python: %PY%
%PY% --version
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
set RC=%ERRORLEVEL%

echo.
if "%RC%"=="0" (
  echo [完成] 安装成功。
) else (
  echo [失败] 退出码 %RC% —— 看上面的输出定位原因。
)
echo.
pause
exit /b %RC%
