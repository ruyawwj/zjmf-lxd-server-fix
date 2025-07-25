#!/bin/bash

# 颜色定义
GREEN="\033[0;32m"
RED="\033[0;31m"
YELLOW="\033[1;33m"
RESET="\033[0m"

info()  { echo -e "${GREEN}[INFO]${RESET} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${RESET} $1"; }
error() { echo -e "${RED}[ERROR]${RESET} $1"; }

# 检查是否为 root
[[ $EUID -ne 0 ]] && error "请使用 root 用户运行本脚本。" && exit 1

# 等待 apt 锁释放
wait_for_apt_lock() {
    echo -e "${YELLOW}[WAIT] 检测到 apt/dpkg 锁，等待释放中...${RESET}"
    while fuser /var/lib/dpkg/lock-frontend >/dev/null 2>&1; do
        sleep 2
        echo -n "."
    done
    echo ""
}

# 安装依赖
install_dependencies() {
    wait_for_apt_lock
    apt update -y

    local packages=(snapd zfsutils-linux btrfs-progs curl wget jq)
    for pkg in "${packages[@]}"; do
        wait_for_apt_lock
        apt install -y "$pkg"
    done
}

# 安装 LXD（通过 snap）
install_lxd() {
    if ! command -v snap >/dev/null 2>&1; then
        error "snapd 未安装或损坏，无法继续安装 LXD。"
        exit 1
    fi

    if ! snap list | grep -q "^lxd"; then
        info "LXD 未安装，正在通过 Snap 安装..."
        snap install lxd
    else
        info "LXD 已通过 Snap 安装。"
    fi
}

# 初始化 LXD
initialize_lxd() {
    if ! lxc info >/dev/null 2>&1; then
        warn "LXD 尚未初始化，开始执行初始化..."
        lxd init --auto
    else
        info "LXD 已初始化。"
    fi
}

# 显示版本
show_version() {
    if command -v lxd >/dev/null 2>&1; then
        version=$(lxd --version)
        info "当前 LXD 版本：$version"
    else
        error "LXD 命令未找到，安装可能失败。"
    fi
}

# 主流程
info "开始检测并安装 LXD 环境..."
install_dependencies
install_lxd
initialize_lxd
show_version
info "LXD 环境检查与安装完成。"
