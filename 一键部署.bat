@echo off
rem ================================================================
rem  Subscribe archive - one-click setup
rem
rem    <this file>          setup
rem    <this file> help     show this text
rem
rem  What it does:
rem    1. check Python
rem    2. create or repair the .venv
rem       (a .venv copied from another machine never works - it is
rem        detected and rebuilt automatically)
rem    3. install Python dependencies (openai, feedparser)
rem    4. verify the CLI loads
rem    5. check config.json and watch_feeds.json
rem    6. optionally start the web UI
rem ================================================================
setlocal
cd /d "%~dp0"

if /i "%~1"=="help" goto :usage
if /i "%~1"=="-h"   goto :usage
if /i "%~1"=="/?"   goto :usage

echo ================================================================
echo   Subscribe archive - setup
echo   Folder: %~dp0
echo ================================================================
echo.

rem ------------------------------------------------- 1. Python
set "PYCMD="
python --version >nul 2>&1
if not errorlevel 1 set "PYCMD=python"
if not defined PYCMD (
    py -3 --version >nul 2>&1
    if not errorlevel 1 set "PYCMD=py -3"
)
if not defined PYCMD goto :err_python

echo [1/5] Python ......... ok
%PYCMD% --version

rem ------------------------------------------------- 2. venv
echo.
echo [2/5] Virtual env ...
set "VPY=%~dp0.venv\Scripts\python.exe"

if exist "%VPY%" (
    "%VPY%" -c "import sys" >nul 2>&1
    if errorlevel 1 (
        echo       existing .venv is NOT usable - rebuilding
        rmdir /s /q "%~dp0.venv"
    )
)

if not exist "%VPY%" (
    echo       creating .venv ...
    %PYCMD% -m venv "%~dp0.venv"
    if errorlevel 1 goto :err_venv
)
echo       ok

rem ------------------------------------------------- 3. dependencies
echo.
echo [3/5] Installing dependencies ^(openai, feedparser^) ...
"%VPY%" -m pip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple
"%VPY%" -m pip install openai feedparser -i https://pypi.tuna.tsinghua.edu.cn/simple
if errorlevel 1 "%VPY%" -m pip install openai feedparser
"%VPY%" -c "import openai, feedparser" >nul 2>&1
if errorlevel 1 goto :err_pip
echo       ok

rem ------------------------------------------------- 4. self check
echo.
echo [4/5] Checking the CLI ...
"%VPY%" "%~dp0src\archive.py" --list-steps >nul 2>&1
if errorlevel 1 goto :err_selfcheck
echo       ok

rem tkinter is needed by the desktop window (src\gui.py); the web UI does not
rem need it. It ships with the python.org installer unless "tcl/tk" was unticked.
"%VPY%" -c "import tkinter" >nul 2>&1
if errorlevel 1 (
    echo       [WARN] tkinter is missing - the desktop window cannot start.
    echo              Re-run the Python installer -^> Modify -^> tick
    echo              "tcl/tk and IDLE", then run this script again.
    echo              The web UI still works.
) else (
    echo       tkinter ^(desktop window^) ... ok
)

rem ------------------------------------------------- 5. config
echo.
echo [5/5] Configuration ...
if exist "%~dp0src\config.json" (
    echo       src\config.json ......................... found
) else (
    echo       [WARN] src\config.json is missing.
    echo              Copy src\config.example.json and fill in api_key / base_url / model.
    echo              Add the "mail" section if you want failure e-mails.
)
if exist "%~dp0src\watch_feeds.json" (
    echo       src\watch_feeds.json .................... found
) else (
    echo       [WARN] src\watch_feeds.json is missing.
    echo              Create it, or add feeds from the web UI (Config page).
)

rem ------------------------------------------------- summary
echo.
echo ================================================================
echo   Setup finished.
echo ================================================================
echo.
echo   Scripts in this folder:
for %%F in ("%~dp0*.bat") do echo     - %%~nxF
echo.
echo   Hints:
echo     * desktop launcher  : opens the small window (archive / open page / quit)
echo.
echo   Note: keep every .bat in this folder PURE ASCII - cmd.exe reads
echo         them in the OEM code page, so UTF-8 Chinese text would break them.
echo.
echo   Reminder: overseas feeds may need a proxy. Set HTTP_PROXY / HTTPS_PROXY
echo             in the environment before running the archive if needed.
echo.

set /p "STARTNOW=Start the desktop window now? [Y/N]: "
if /i "%STARTNOW%"=="Y" (
    echo Starting the desktop window ...
    start "" ".venv\Scripts\pythonw.exe" "src\gui.py"
)

echo.
echo Done.
pause
exit /b 0

:usage
echo Usage:
echo   %~nx0          setup
echo   %~nx0 help     this text
pause
exit /b 0

:err_python
echo.
echo [ERROR] Python not found.
echo         Install Python 3.10+ from https://www.python.org/downloads/windows/
echo         and tick "Add python.exe to PATH" during setup.
echo.
pause
exit /b 1

:err_venv
echo.
echo [ERROR] Failed to create the virtual environment.
echo         Try: %PYCMD% -m venv "%~dp0.venv"
echo.
pause
exit /b 1

:err_pip
echo.
echo [ERROR] Dependency installation failed (openai / feedparser missing).
echo         Check your network, then retry this script.
echo.
pause
exit /b 1

:err_selfcheck
echo.
echo [ERROR] "src\archive.py --list-steps" failed.
echo         The environment is incomplete - see the message above.
echo.
pause
exit /b 1
