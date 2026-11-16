@echo off
rem Would I Lie to You? - start the game. Double-click to run.
cd /d "%~dp0"
title Would I Lie to You?

if not exist ".venv\Scripts\python.exe" (
    echo The game is not installed yet. Double-click install.bat first.
    pause
    exit /b 1
)

echo Starting Would I Lie to You? at http://127.0.0.1:5050
echo Keep this window open while playing. Close it to stop the game.
start "" cmd /c "timeout /t 3 /nobreak >nul & start http://127.0.0.1:5050"
".venv\Scripts\python.exe" app.py
pause
