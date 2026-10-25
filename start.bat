@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"
title AQuant Studio
set "ROOT=%~dp0"
set "BACKEND=%ROOT%web_app\backend"
set "RUNTIME=%BACKEND%\runtime"
set "VENV=%BACKEND%\.venv"
set "PORT=8000"
set "URL=http://127.0.0.1:%PORT%/"
if not exist "%RUNTIME%" mkdir "%RUNTIME%"

:: ---- Already running? Just open the page ----
netstat -ano | findstr /r /c:":%PORT% .*LISTENING" >nul 2>nul
if not errorlevel 1 (
  echo 端口 %PORT% 已经在使用，可能程序已在运行，直接打开 %URL%
  start "" "%URL%"
  timeout /t 3 >nul
  exit /b 0
)

:: ---- Reuse the virtual environment if it exists ----
if exist "%VENV%\Scripts\python.exe" (
  set "VPY=%VENV%\Scripts\python.exe"
  goto :deps
)

:: ---- Locate Python 3.11+ ----
set "PY="
if exist "%RUNTIME%\python_path.txt" set /p PY=<"%RUNTIME%\python_path.txt"
if defined PY call :check "%PY%" && goto :found
set "PY="
for %%P in (
  "%USERPROFILE%\miniconda3\python.exe"
  "%USERPROFILE%\anaconda3\python.exe"
  "%LOCALAPPDATA%\miniconda3\python.exe"
  "%LOCALAPPDATA%\anaconda3\python.exe"
  "%ProgramData%\miniconda3\python.exe"
  "%ProgramData%\anaconda3\python.exe"
  "C:\Users\Public\Miniconda3\python.exe"
  "C:\Users\Public\Anaconda3\python.exe"
  "D:\miniconda3\python.exe"
  "D:\anaconda3\python.exe"
  "E:\miniconda3\python.exe"
  "E:\anaconda3\python.exe"
) do (
  if not defined PY if exist %%P call :check %%P && set "PY=%%~P"
)
if defined PY goto :found
if exist "%USERPROFILE%\.conda\environments.txt" (
  for /f "usebackq delims=" %%L in ("%USERPROFILE%\.conda\environments.txt") do (
    if not defined PY if exist "%%L\python.exe" call :check "%%L\python.exe" && set "PY=%%L\python.exe"
  )
)
if defined PY goto :found
for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do (
  if not defined PY if exist "%%D\python.exe" call :check "%%D\python.exe" && set "PY=%%D\python.exe"
)
if defined PY goto :found
where py >nul 2>nul && py -3 -c "import sys; sys.exit(0 if sys.version_info>=(3,11) else 1)" >nul 2>nul && set "PY=py -3"
if defined PY goto :found
call :check python && set "PY=python"
if defined PY goto :found
if exist "%USERPROFILE%\.cache\codex-runtimes" (
  for /r "%USERPROFILE%\.cache\codex-runtimes" %%F in (python.exe) do (
    if not defined PY if exist "%%F" call :check "%%F" && set "PY=%%F"
  )
)
if defined PY goto :found
echo.
echo [错误] 没有找到 Python 3.11 或更高版本。
echo 请安装 Python 3.11+（https://www.python.org/downloads/ ，安装时勾选 Add python.exe to PATH）或 Miniconda，
echo 或者把 python.exe 的完整路径写进 web_app\backend\runtime\python_path.txt 后重试。
pause
exit /b 1

:found
if "%PY%"=="py -3" (set "PYRUN=py -3") else (set PYRUN="%PY%")
echo 使用 Python：%PY%
if not "%PY%"=="py -3" (echo %PY%> "%RUNTIME%\python_path.txt")

:: ---- Create a private virtual environment (falls back to the found Python) ----
echo 首次运行：创建虚拟环境 web_app\backend\.venv ...
%PYRUN% -m venv "%VENV%" >nul 2>nul
if exist "%VENV%\Scripts\python.exe" (
  set "VPY=%VENV%\Scripts\python.exe"
) else (
  echo [提示] 无法创建虚拟环境，直接使用找到的 Python 安装依赖。
  if "%PY%"=="py -3" (
    for /f "delims=" %%E in ('py -3 -c "import sys; print(sys.executable)"') do set "VPY=%%E"
  ) else (
    set "VPY=%PY%"
  )
)

:deps
:: ---- Dependencies: (re)install when missing or when requirements.txt changed ----
set "REQ=%BACKEND%\requirements.txt"
set "STAMP=%RUNTIME%\requirements.installed.txt"
set "NEED_INSTALL=0"
"%VPY%" -c "import fastapi, uvicorn, sqlalchemy, alembic, pydantic_settings, multipart, exchange_calendars" >nul 2>nul
if errorlevel 1 set "NEED_INSTALL=1"
if not exist "%STAMP%" set "NEED_INSTALL=1"
if exist "%STAMP%" fc /b "%REQ%" "%STAMP%" >nul 2>nul || set "NEED_INSTALL=1"
if "%NEED_INSTALL%"=="1" (
  echo 安装依赖，第一次大约需要 1 到 3 分钟 ...
  "%VPY%" -m pip install --disable-pip-version-check -r "%REQ%"
  if errorlevel 1 (
    echo 默认源安装失败，改用清华镜像重试 ...
    "%VPY%" -m pip install --disable-pip-version-check -r "%REQ%" -i https://pypi.tuna.tsinghua.edu.cn/simple
  )
  "%VPY%" -c "import fastapi, uvicorn, sqlalchemy, alembic, pydantic_settings, multipart, exchange_calendars" >nul 2>nul
  if errorlevel 1 (
    echo.
    echo [错误] 依赖安装失败，请检查网络后重新双击 start.bat。
    pause
    exit /b 1
  )
  copy /y "%REQ%" "%STAMP%" >nul
)

:: ---- Start ----
if not exist "%ROOT%web_app\frontend\dist\index.html" (
  echo [提示] 没有找到网页文件 web_app\frontend\dist，只能打开接口文档 %URL%docs
)
echo.
echo 正在启动 AQuant Studio：%URL%
echo 第一个注册的账户会自动成为管理员。关闭此窗口即停止程序。
echo.
start "" /min cmd /c "timeout /t 5 /nobreak >nul & start "" %URL%"
cd /d "%BACKEND%"
"%VPY%" -m uvicorn app.main:app --host 127.0.0.1 --port %PORT%
echo.
echo 程序已退出。如果上面有报错，请截图发给开发者。
pause
exit /b 0

:check
%1 -c "import sys; sys.exit(0 if sys.version_info>=(3,11) else 1)" >nul 2>nul
exit /b %errorlevel%
