@echo off
cd /d "%~dp0"
call .venv\Scripts\activate.bat

:restart
echo [%date% %time%] Starting Reporter...
python tick_reporter.py
echo [%date% %time%] Reporter exited. Restarting in 5s... (Ctrl+C to cancel)
timeout /t 5 /nobreak >nul
goto restart
