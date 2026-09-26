@echo off
chcp 65001 >nul
cd /d "%~dp0..\frontend"
echo ============================================
echo   筑安云前端启动中... http://localhost:5173
echo ============================================
call npm run dev
pause
