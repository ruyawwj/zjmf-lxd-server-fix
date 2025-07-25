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

# 国内优先的外网 IP 接口列表
ip_services=(
    "https://myip.ipip.net"
    "https://api.myip.la"
    "https://www.trackip.net/ip"
    "https://www.cloudflare.com/cdn-cgi/trace"
    "https://api64.ipify.org"
    "https://ip.sb"
    "https://ifconfig.me"
    "https://ipv4.icanhazip.com"
    "https://checkip.amazonaws.com"
)

get_ip() {
    for service in "${ip_services[@]}"; do
        result=$(curl -s --max-time 5 "$service" || wget -qO- "$service")

        if echo "$result" | grep -q "^ip="; then
            echo "$result" | grep '^ip=' | cut -d '=' -f2
            return 0
        fi

        if echo "$result" | grep -q "当前 IP"; then
            echo "$result" | grep -oE '([0-9]{1,3}\.){3}[0-9]{1,3}'
            return 0
        fi

        if [[ "$result" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
            echo "$result"
            return 0
        fi
    done

    echo "获取外网IP失败"
    return 1
}

external_ip=$(get_ip)

# ANSI 颜色代码
GREEN="\e[32m"
YELLOW="\e[33m"
RESET="\e[0m"

# 显示配置
echo -e "========== app.ini 配置 =========="
echo -e "管理后台地址: ${GREEN}http://$external_ip:$port${RESET}"
echo -e "登录密码:     ${YELLOW}$api_token${RESET}"
echo -e "=================================="