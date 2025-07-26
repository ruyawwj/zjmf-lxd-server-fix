#!/bin/bash

set -e

REPO_DIR="zjmf-lxd-server-fix"
SERVER_SUBDIR="$REPO_DIR/server"

if [ -d "$SERVER_SUBDIR" ]; then
  read -rp "[WARN] 目录 $SERVER_SUBDIR 已存在，是否覆盖重新拉取？(Y/N): " yn
  if [[ $yn =~ ^[Yy]$ ]]; then
    echo "[INFO] 删除旧目录..."
    rm -rf "$REPO_DIR"
    echo "[INFO] 正在拉取 Git 仓库中的 server 目录..."
    git clone --no-checkout https://github.com/StarVM-OpenSource/zjmf-lxd-server-fix.git
    cd "$REPO_DIR"
    git sparse-checkout init --cone
    git sparse-checkout set server
    git checkout
    rm -rf .git README.md install.sh
  else
    echo "[INFO] 保留旧目录，跳过拉取操作。"
    cd "$SERVER_SUBDIR"
  fi
else
  echo "[INFO] 目录不存在，开始拉取 Git 仓库中的 server 目录..."
  git clone --no-checkout https://github.com/StarVM-OpenSource/zjmf-lxd-server-fix.git
  cd "$REPO_DIR"
  git sparse-checkout init --cone
  git sparse-checkout set server
  git checkout
  rm -rf .git README.md install.sh
fi

# --- 获取默认外网网卡和该网卡内IP ---
get_default_interface() {
    ip route get 8.8.8.8 2>/dev/null | awk '/dev/ {for(i=1;i<=NF;i++){if($i=="dev"){print $(i+1);exit}}}'
}
get_interface_ip() {
    local iface=$1
    ip -4 addr show dev "$iface" | grep -oP '(?<=inet\s)\d+(\.\d+){3}' | head -1
}

MAIN_INTERFACE=$(get_default_interface)
NAT_LISTEN_IP=$(get_interface_ip "$MAIN_INTERFACE")

echo "[INFO] 发现默认网卡: $MAIN_INTERFACE"
echo "[INFO] 网卡 $MAIN_INTERFACE 的IPv4地址: $NAT_LISTEN_IP"

# --- 用户输入 HTTP_PORT ---
while true; do
    read -rp "请输入 HTTP_PORT (1-65535), 留空则随机生成: " HTTP_PORT
    if [[ -z "$HTTP_PORT" ]]; then
        HTTP_PORT=$(( RANDOM % 9000 + 1000 ))
        echo "[INFO] 随机生成的 HTTP_PORT 为: $HTTP_PORT"
        break
    elif [[ "$HTTP_PORT" =~ ^[1-9][0-9]{0,4}$ ]] && [ "$HTTP_PORT" -le 65535 ]; then
        echo "[INFO] 使用用户输入的 HTTP_PORT: $HTTP_PORT"
        break
    else
        echo "[ERROR] 请输入有效的端口号（1-65535）"
    fi
done

# --- 用户输入 TOKEN ---
generate_token() {
    local len=15
    tr -dc 'A-Z0-9' < /dev/urandom | head -c $len
}

while true; do
    read -rp "请输入 TOKEN (大写字母和数字, 留空则随机生成15位): " TOKEN
    if [[ -z "$TOKEN" ]]; then
        TOKEN=$(generate_token)
        echo "[INFO] 随机生成的 TOKEN: $TOKEN"
        break
    elif [[ "$TOKEN" =~ ^[A-Z0-9]{15}$ ]]; then
        echo "[INFO] 使用用户输入的 TOKEN: $TOKEN"
        break
    else
        echo "[ERROR] TOKEN 必须是15位大写字母和数字组合。"
    fi
done

# --- 写入 app.ini 配置 ---
cat > /root/zjmf-lxd-server-fix/server/app.ini <<EOF
[server]
HTTP_PORT = $HTTP_PORT
TOKEN = $TOKEN
LOG_LEVEL = ERROR

[lxc]
DEFAULT_IMAGE_ALIAS = debian12-arm64-ssh
NETWORK_BRIDGE = lxdbr0
STORAGE_POOL = btrfs-pool
DEFAULT_CONTAINER_USER = root
MAIN_INTERFACE = $MAIN_INTERFACE
NAT_LISTEN_IP = $NAT_LISTEN_IP
EOF

echo "[INFO] app.ini 配置文件写入完成."

# --- 安装 python3-pip 和 flask ---
echo "[INFO] 安装脚本依赖..."
apt update -y
apt install -y python3-pip python3-flask
pip3 install pylxd --break-system-packages

# --- 创建/更新 systemd 服务 ---
SERVICE_FILE=/etc/systemd/system/lxd-api.service

if [ -f "$SERVICE_FILE" ]; then
    echo "[INFO] 发现已存在的 lxd-api.service，正在停止并删除旧服务..."
    systemctl stop lxd-api.service || true
    systemctl disable lxd-api.service || true
    rm -f "$SERVICE_FILE"
    systemctl daemon-reload
    echo "[INFO] 旧服务已删除."
fi

echo "[INFO] 创建新的 lxd-api.service..."
cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=LXD Management API Service
After=network.target

[Service]
User=root
Group=root
WorkingDirectory=/root/zjmf-lxd-server-fix/server
ExecStart=/usr/bin/python3 app.py
Restart=always

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable lxd-api
systemctl restart lxd-api
systemctl status lxd-api

echo "[INFO] 脚本执行完成。"
echo "[INFO] 如服务未正常启动，请手动执行 systemctl restart lxd-api 以确保服务正常启动，如还无法启动请发issues"
