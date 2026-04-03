@echo off
REM DeepSeek 监控系统启动脚本 (Windows)

REM 获取脚本所在目录
set SCRIPT_DIR=%~dp0
set PROJECT_DIR=%SCRIPT_DIR%..

REM 进入项目目录
cd /d "%PROJECT_DIR%"

echo ==========================================
echo   DeepSeek 网页端变化追踪系统
echo ==========================================
echo.

REM 检查 Python 环境
where python >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo ❌ 错误: 未找到 Python
    echo 请先安装 Python 3.8 或更高版本
    pause
    exit /b 1
)

echo ✅ Python 版本:
python --version
echo.

REM 检查虚拟环境
if not exist "venv\" (
    echo.
    echo 📦 创建虚拟环境...
    python -m venv venv

    if %ERRORLEVEL% NEQ 0 (
        echo ❌ 创建虚拟环境失败
        pause
        exit /b 1
    )

    echo ✅ 虚拟环境创建成功
)

REM 激活虚拟环境
echo 🔌 激活虚拟环境...
call venv\Scripts\activate.bat

REM 检查依赖
echo 🔍 检查依赖...
python -c "import playwright" 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo 📥 安装依赖...
    pip install -r requirements.txt

    if %ERRORLEVEL% NEQ 0 (
        echo ❌ 依赖安装失败
        pause
        exit /b 1
    )

    echo ✅ 依赖安装成功
)

REM 检查 Playwright 浏览器
playwright install chromium >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo 🌐 安装 Playwright 浏览器...
    playwright install chromium

    if %ERRORLEVEL% NEQ 0 (
        echo ❌ 浏览器安装失败
        pause
        exit /b 1
    )

    echo ✅ 浏览器安装成功
)

REM 选择运行模式
echo.
echo 请选择运行模式:
echo   1) 完整检查 (前端 + 配置 + 行为)
echo   2) 仅前端检查 (快速)
echo   3) 生成报告
echo   4) 持续监控
echo.
set /p mode="请输入选项 [1-4]: "

if "%mode%"=="1" (
    echo.
    echo 🚀 运行完整监控检查...
    python scripts\monitor.py --mode full
) else if "%mode%"=="2" (
    echo.
    echo 🚀 运行前端资源检查...
    python scripts\monitor.py --mode frontend
) else if "%mode%"=="3" (
    echo.
    set /p days="报告覆盖天数 [默认: 7]: "
    if "%days%"=="" set days=7
    echo.
    echo 📊 生成报告 (过去 %days% 天)...
    python scripts\monitor.py --mode report --report-days %days%
) else if "%mode%"=="4" (
    echo.
    echo 🔄 启动持续监控模式...
    echo 按 Ctrl+C 停止监控
    echo.
    python scripts\monitor.py --mode continuous
) else (
    echo ❌ 无效的选项
    pause
    exit /b 1
)

REM 退出码
set exit_code=%ERRORLEVEL%

echo.
if %exit_code%==0 (
    echo ✅ 执行完成
) else (
    echo ❌ 执行失败 (退出码: %exit_code%)
)

pause
