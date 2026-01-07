@echo off
REM Batch script to start the development watcher (Windows CMD)
IF EXIST "%~dp0\..\.venv\Scripts\activate.bat" (
    call "%~dp0\..\.venv\Scripts\activate.bat"
) ELSE (
    echo Warning: virtualenv activate.bat not found. Ensure your environment is active.
)

echo Starting watcher...
python -u "scripts\watcher_restart.py" --cmd "python main.py" --paths . core web utils config data
pause
