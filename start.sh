#!/bin/bash
# 选股平台启动脚本

cd /root/stock-screener

# 安装依赖
pip3 install flask requests -q

# 启动
echo "启动选股平台..."
python3 web_server.py
