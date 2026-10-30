@echo off
chcp 65001 >nul
cd /d "%~dp0"

REM 创建虚拟环境（如不存在）
if not exist ".venv" (
    echo 创建虚拟环境 .venv ...
    python -m venv .venv
)

REM 激活虚拟环境
call .venv\Scripts\activate.bat

REM 安装依赖
echo 安装依赖 ...
pip install -r requirements.txt

REM 启动服务（长连接模式）
echo 启动 SRE 运维问答机器人 ...
python -m src.start_lark
