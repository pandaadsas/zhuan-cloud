@echo off
chcp 65001 >nul
cd /d "%~dp0..\backend"
echo ============================================
echo   筑安云后端启动中... http://127.0.0.1:8000
echo ============================================
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port 8000
pause
