#!/bin/bash
# DeepSeek 监控系统启动脚本 (Linux/macOS)

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# 进入项目目录
cd "$PROJECT_DIR"

echo "=========================================="
echo "  DeepSeek 网页端变化追踪系统"
echo "=========================================="
echo ""

# 检查 Python 环境
if ! command -v python3 &> /dev/null; then
    echo "❌ 错误: 未找到 Python3"
    echo "请先安装 Python 3.8 或更高版本"
    exit 1
fi

echo "✅ Python 版本: $(python3 --version)"

# 检查虚拟环境
if [ ! -d "venv" ]; then
    echo ""
    echo "📦 创建虚拟环境..."
    python3 -m venv venv

    if [ $? -ne 0 ]; then
        echo "❌ 创建虚拟环境失败"
        exit 1
    fi

    echo "✅ 虚拟环境创建成功"
fi

# 激活虚拟环境
echo "🔌 激活虚拟环境..."
source venv/bin/activate

# 检查依赖
echo "🔍 检查依赖..."
if ! python -c "import playwright" 2>/dev/null; then
    echo ""
    echo "📥 安装依赖..."
    pip install -r requirements.txt

    if [ $? -ne 0 ]; then
        echo "❌ 依赖安装失败"
        exit 1
    fi

    echo "✅ 依赖安装成功"
fi

# 检查 Playwright 浏览器
if ! playwright install chromium &>/dev/null; then
    echo ""
    echo "🌐 安装 Playwright 浏览器..."
    playwright install chromium

    if [ $? -ne 0 ]; then
        echo "❌ 浏览器安装失败"
        exit 1
    fi

    echo "✅ 浏览器安装成功"
fi

# 选择运行模式
echo ""
echo "请选择运行模式:"
echo "  1) 完整检查 (前端 + 配置 + 行为)"
echo "  2) 仅前端检查 (快速)"
echo "  3) 生成报告"
echo "  4) 持续监控"
echo ""
read -p "请输入选项 [1-4]: " mode

case $mode in
    1)
        echo ""
        echo "🚀 运行完整监控检查..."
        python scripts/monitor.py --mode full
        ;;
    2)
        echo ""
        echo "🚀 运行前端资源检查..."
        python scripts/monitor.py --mode frontend
        ;;
    3)
        echo ""
        read -p "报告覆盖天数 [默认: 7]: " days
        days=${days:-7}
        echo ""
        echo "📊 生成报告 (过去 $days 天)..."
        python scripts/monitor.py --mode report --report-days $days
        ;;
    4)
        echo ""
        echo "🔄 启动持续监控模式..."
        echo "按 Ctrl+C 停止监控"
        echo ""
        python scripts/monitor.py --mode continuous
        ;;
    *)
        echo "❌ 无效的选项"
        exit 1
        ;;
esac

# 退出码
exit_code=$?

echo ""
if [ $exit_code -eq 0 ]; then
    echo "✅ 执行完成"
else
    echo "❌ 执行失败 (退出码: $exit_code)"
fi

exit $exit_code
