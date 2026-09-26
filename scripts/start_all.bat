@echo off
chcp 65001 >nul
echo 启动筑安云（后端 + 前端开发服务）...
start "筑安云后端" cmd /k "%~dp0start_backend.bat"
timeout /t 3 >nul
start "筑安云前端" cmd /k "%~dp0start_frontend.bat"
echo 已启动：后端 http://127.0.0.1:8000 ｜ 前端 http://localhost:5173
