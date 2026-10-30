#!/usr/bin/env bash
set -e

# 进入脚本所在目录
cd "$(dirname "$0")"

# 创建虚拟环境（如不存在）
if [ ! -d ".venv" ]; then
    echo "创建虚拟环境 .venv ..."
    python3 -m venv .venv
fi

# 激活虚拟环境
source .venv/bin/activate

# 安装依赖
echo "安装依赖 ..."
pip install -r requirements.txt

# 启动服务（长连接模式）
echo "启动 SRE 运维问答机器人 ..."
python -m src.start_lark
