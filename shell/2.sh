#!/bin/bash
set -o errexit
set -o nounset
set -o pipefail

readonly COLOR_RESET='\033[0m'
readonly COLOR_GREEN='\033[0;32m'
readonly COLOR_YELLOW='\033[1;33m'
readonly COLOR_RED='\033[0;31m'
readonly COLOR_BLUE='\033[0;34m'

msg() {
    local color_name="$1"
    local message="$2"
    local color_var="COLOR_${color_name^^}"
    printf '%b%s%b\n' "${!color_var}" "${message}" "${COLOR_RESET}"
}

check_root() {
    if [[ "$(id -u)" -ne 0 ]]; then
        msg "RED" "错误: 请使用 root 权限运行此脚本。"
        exit 1
    fi
}

check_dependencies() {
    msg "BLUE" "检测并安装必要依赖..."
    local deps=(btrfs-progs curl jq snapd)
    local to_install=()
    for dep in "${deps[@]}"; do
        if ! command -v "$dep" &>/dev/null; then
            to_install+=("$dep")
        fi
    done
    if [ ${#to_install[@]} -gt 0 ]; then
        msg "YELLOW" "缺少依赖: ${to_install[*]}，尝试自动安装..."
        apt-get update
        apt-get install -y "${to_install[@]}"
    else
        msg "GREEN" "依赖检测通过。"
    fi
}

install_lxd() {
    if command -v lxd &>/dev/null; then
        msg "GREEN" "LXD 已安装，版本: $(lxd --version)"
        return 0
    fi
    msg "BLUE" "开始通过 snap 安装 LXD..."
    snap install core
    snap install lxd

    # 添加 snap 路径
    export PATH=$PATH:/snap/bin

    msg "BLUE" "初始化 LXD..."
    lxd init --auto
    msg "GREEN" "LXD 安装并初始化完成。版本: $(lxd --version)"
}


create_btrfs_pool() {
    local pool_name="btrfs-pool"
    msg "BLUE" "创建 BTRFS 存储池: $pool_name"
    read -p "$(msg "YELLOW" "请输入存储池大小(GB，正整数): ")" size
    size=${size:-20}
    if ! [[ "$size" =~ ^[1-9][0-9]*$ ]]; then
        msg "RED" "无效的大小输入，必须为正整数。"
        exit 1
    fi
    if lxc storage list | grep -qw "$pool_name"; then
        msg "YELLOW" "存储池 $pool_name 已存在，跳过创建。"
        return
    fi
    msg "BLUE" "正在创建存储池，大小: ${size}GB..."
    lxc storage create "$pool_name" btrfs size="${size}GB"
    msg "GREEN" "[INFO] 存储池 '$pool_name' 创建成功！"
}

set_lxd_pool_as_default() {
    local pool_name="$1"
    msg "BLUE" "设置默认 profile 根磁盘池为 '$pool_name'..."
    if lxc profile show default | grep -q 'root:'; then
        msg "YELLOW" "检测到已有 root 设备，正在删除..."
        lxc profile device remove default root || {
            msg "RED" "删除 root 设备失败，操作终止。"
            exit 1
        }
    else
        msg "YELLOW" "默认 profile 目前无 root 设备。"
    fi

    if lxc profile device add default root disk path=/ pool="$pool_name"; then
        msg "GREEN" "成功将默认 profile 根磁盘设备设置为存储池 '$pool_name'。"
    else
        msg "RED" "添加 root 设备失败。"
        exit 1
    fi
}

main() {
    check_root
    check_dependencies
    install_lxd
    create_btrfs_pool
    set_lxd_pool_as_default "btrfs-pool"
    msg "GREEN" "脚本执行完毕。"
}

main "$@"
