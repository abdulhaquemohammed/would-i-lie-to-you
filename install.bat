@echo off
rem Would I Lie to You? - Windows installer. Double-click to run.
cd /d "%~dp0"
title Would I Lie to You? - Install

rem Find Python 3.10+ (py launcher first, then python on PATH)
set "PY="
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1 && set "PY=py -3"
if not defined PY python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1 && set "PY=python"
if not defined PY (
    echo Python 3.10 or newer was not found.
    echo Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH".
    echo Then run install.bat again.
    pause
    exit /b 1
)

echo Creating virtual environment...
if not exist ".venv\Scripts\python.exe" %PY% -m venv .venv
if errorlevel 1 goto :fail

echo Installing packages...
".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :fail

if exist ".env" goto :done
echo Creating .env with a random secret key...
".venv\Scripts\python.exe" -c "import secrets, pathlib; t = pathlib.Path('.env.example').read_text(); pathlib.Path('.env').write_text(t.replace('change-me-to-something-random', secrets.token_hex(32)))"
if errorlevel 1 goto :fail

:done
echo.
echo Install complete. Double-click run.bat to start the game.
pause
exit /b 0

:fail
echo.
echo Install failed. See the error above and the Troubleshooting section of the installation guide.
pause
exit /b 1
