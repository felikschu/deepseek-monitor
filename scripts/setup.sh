#!/bin/bash
# DeepSeek Monitor 安装脚本
# 创建桌面快捷方式（仅 macOS）

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "🛡️  DeepSeek Monitor 安装"
echo "============================"
echo ""

# 1. 检查 Python
if ! command -v python3 &>/dev/null; then
    echo "❌ 未找到 python3，请先安装 Python 3.8+"
    echo "   https://www.python.org/downloads/"
    exit 1
fi
echo "✅ Python: $(python3 --version)"

# 2. 安装依赖
echo ""
echo "📦 安装依赖..."
pip3 install -q aiohttp loguru pyyaml beautifulsoup4 2>/dev/null || \
pip install -q aiohttp loguru pyyaml beautifulsoup4 2>/dev/null
echo "✅ 依赖已安装"

# 3. 创建桌面快捷方式（仅 macOS）
if [[ "$OSTYPE" == "darwin"* ]]; then
    DESKTOP="$HOME/Desktop"
    SHORTCUT="$DESKTOP/DeepSeek Monitor.command"

    cat > "$SHORTCUT" << SHORTCUT_EOF
#!/bin/bash
# DeepSeek Monitor Dashboard - 双击即可启动
PROJECT="$PROJECT_DIR"
osascript -e "
tell application \"Terminal\"
    activate
    do script \"cd '\$PROJECT' && python3 web/server.py; exit\"
end tell"
SHORTCUT_EOF

    chmod +x "$SHORTCUT"
    echo "✅ 桌面快捷方式已创建: $SHORTCUT"
else
    echo "ℹ️  非 macOS 系统，跳过桌面快捷方式"
    echo "   启动方式: cd $PROJECT_DIR && python3 web/server.py"
fi

echo ""
echo "🎉 安装完成！"
echo ""
echo "启动方式："
if [[ "$OSTYPE" == "darwin"* ]]; then
    echo "  方式1: 双击桌面「DeepSeek Monitor.command」"
fi
echo "  方式2: cd $PROJECT_DIR && python3 web/server.py"
echo ""
echo "启动后打开 http://localhost:8765 查看 Dashboard"
