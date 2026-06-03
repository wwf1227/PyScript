@echo off
cd /d "%~dp0"
call venv\Scripts\activate.bat

:restart
echo [%date% %time%] Starting Writer...
python tick_writer.py
echo [%date% %time%] Writer exited. Restarting in 5s... (Ctrl+C to cancel)
timeout /t 5 /nobreak >nul
goto restart
