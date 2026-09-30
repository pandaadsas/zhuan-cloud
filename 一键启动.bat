@echo off
chcp 65001 >nul
title 筑安云
cd /d "%~dp0backend"

if not exist ".venv\Scripts\python.exe" (
    echo.
    echo  首次运行：正在创建虚拟环境并安装依赖（约2-5分钟，仅需一次）...
    echo.
    python -m venv .venv || (echo 未找到Python，请先安装 Python 3.11+ 并勾选 Add to PATH & pause & exit /b 1)
    ".venv\Scripts\python.exe" -m pip install -q -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/
)

echo.
echo  ================================================
echo   筑安云启动中...  浏览器将自动打开
echo   本机访问： http://127.0.0.1:8000
echo   局域网访问： http://本机IP:8000  （供队友访问）
echo   演示账号： zhangmin / liqiang / zeren01 等
echo              密码均为 123456
echo  ================================================
echo.
start "" cmd /c "timeout /t 6 /nobreak >nul & start http://127.0.0.1:8000"
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port 8000
pause
