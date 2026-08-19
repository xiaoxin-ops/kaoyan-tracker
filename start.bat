@echo off
rem ============================================================
rem  研途 · 考研学习进度追踪  一键启动脚本
rem  优先使用项目内置便携 Python（.runtime），否则使用系统 Python
rem ============================================================
chcp 65001 >nul
cd /d "%~dp0"

set PY=

if exist ".runtime\python\python.exe" (
    set "PY=.runtime\python\python.exe"
    goto :run
)

where python >nul 2>nul
if %errorlevel%==0 (
    set "PY=python"
    goto :deps
)

echo [错误] 未检测到 Python 环境。
echo   方案一：安装 Python 3.10+（https://www.python.org/downloads/ 勾选 Add to PATH）
echo   方案二：保留项目内的 .runtime 便携运行环境（请勿删除）
pause
exit /b 1

:deps
"%PY%" -c "import flask, flask_sqlalchemy" >nul 2>nul
if errorlevel 1 (
    echo 首次运行，正在安装依赖...
    "%PY%" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [错误] 依赖安装失败，请检查网络后重试。
        pause
        exit /b 1
    )
)

:run
"%PY%" app.py
pause
