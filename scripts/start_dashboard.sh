#!/bin/bash
# DeepSeek Monitor Dashboard 启动脚本

cd "$(dirname "$0")/.."
PROJECT_DIR="$(pwd)"
VENV_DIR="$PROJECT_DIR/venv"

echo "🛡️  DeepSeek Monitor Dashboard"
echo "================================"

# 优先使用系统 Python（已装好依赖），跳过 venv
# 如果系统 Python 有 aiohttp 就直接用，否则创建 venv
if python3 -c "import aiohttp" 2>/dev/null; then
    echo "✅ 使用系统 Python 环境"
else
    echo "📦 系统缺少依赖，使用虚拟环境..."

    # 创建虚拟环境（如不存在）
    if [ ! -d "$VENV_DIR" ]; then
        echo "   创建虚拟环境..."
        python3 -m venv "$VENV_DIR" || { echo "❌ 创建虚拟环境失败"; exit 1; }
    fi

    # 激活虚拟环境
    source "$VENV_DIR/bin/activate"

    # 安装依赖（显示进度）
    if ! python3 -c "import aiohttp" 2>/dev/null; then
        echo "   安装依赖（首次可能需要 1-2 分钟）..."
        pip install aiohttp loguru pyyaml beautifulsoup4 2>&1 | while read -r line; do
            # 只显示关键信息
            if [[ "$line" == *"Successfully"* ]] || [[ "$line" == *"Requirement already"* ]] || [[ "$line" == *"error"* ]]; then
                echo "   $line"
            fi
        done
        echo "✅ 依赖安装完成"
    fi
fi

# 验证关键依赖
if ! python3 -c "import aiohttp, loguru" 2>/dev/null; then
    echo "❌ 依赖安装失败，请手动运行:"
    echo "   pip install aiohttp loguru pyyaml beautifulsoup4"
    exit 1
fi

# 启动服务
echo ""
echo "🚀 启动 Dashboard..."
echo "   地址: http://localhost:8765"
echo "   按 Ctrl+C 停止"
echo ""

python3 "$PROJECT_DIR/web/server.py" "$@"
