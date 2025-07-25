#!/bin/bash

INI_FILE="/root/zjmf-lxd-server-fix/server/app.ini"

# 检查配置文件是否存在
if [[ ! -f "$INI_FILE" ]]; then
    echo -e "\e[31m[错误] 被控未安装，请先安装后重试。\e[0m"
    exit 1
fi

# 读取配置
port=$(awk -F= '/^HTTP_PORT[[:space:]]*=/ {gsub(/[[:space:]]/, "", $2); print $2}' "$INI_FILE")
api_token=$(awk -F= '/^TOKEN[[:space:]]*=/ {gsub(/[[:space:]]/, "", $2); print $2}' "$INI_FILE")

# ANSI 颜色代码
GREEN="\e[32m"
YELLOW="\e[33m"
RESET="\e[0m"

# 显示配置
echo -e "========== app.ini 配置 =========="
echo -e "对接端口:     ${GREEN}$port${RESET}"
echo -e "对接密钥:     ${YELLOW}$api_token${RESET}"
echo -e "=================================="