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

    if ! systemctl is-active --quiet snapd; then
        systemctl enable --now snapd
    fi
}

setup_snap_path() {
    export PATH=$PATH:/snap/bin

    # 持久化 PATH 设置，避免用户下次登录找不到 snap 命令
    grep -q '/snap/bin' /etc/profile || echo 'export PATH=$PATH:/snap/bin' >> /etc/profile
    grep -q '/snap/bin' /root/.bashrc || echo 'export PATH=$PATH:/snap/bin' >> /root/.bashrc
}

install_lxd() {
    setup_snap_path

    if command -v lxd &>/dev/null; then
        msg "GREEN" "LXD 已安装，版本: $(lxd --version)"
        return 0
    fi

    msg "BLUE" "开始通过 snap 安装 LXD..."
    snap install core
    snap install lxd

    msg "BLUE" "等待 snap 服务准备完成..."
    sleep 5

    msg "BLUE" "初始化 LXD..."
    lxd init --auto || {
        msg "RED" "LXD 初始化失败，终止脚本。"
        exit 1
    }

    msg "GREEN" "LXD 安装并初始化完成，版本: $(lxd --version)"
}

create_btrfs_pool() {
    local pool_name="btrfs-pool"
    read -erp "请输入存储池大小 (单位: GB，正整数，默认 20): " size
    size=${size:-20}

    if ! [[ "$size" =~ ^[1-9][0-9]*$ ]]; then
        msg "RED" "无效的大小输入，必须为正整数。"
        exit 1
    fi

    if lxc storage list | grep -qw "$pool_name"; then
        msg "YELLOW" "存储池 $pool_name 已存在，跳过创建。"
        return
    fi

    msg "BLUE" "正在创建存储池，名称: $pool_name，大小: ${size}GB..."
    lxc storage create "$pool_name" btrfs size="${size}GB" || {
        msg "RED" "创建存储池失败。"
        exit 1
    }

    msg "GREEN" "存储池 '$pool_name' 创建成功！"
}

set_lxd_pool_as_default() {
    local pool_name="$1"
    msg "BLUE" "设置默认 profile 的根磁盘为存储池 '$pool_name'..."

    if lxc profile show default | grep -q 'root:'; then
        msg "YELLOW" "检测到默认 profile 已存在 root 设备，正在删除..."
        lxc profile device remove default root || {
            msg "RED" "删除默认 profile 的 root 设备失败。"
            exit 1
        }
    fi

    lxc profile device add default root disk path=/ pool="$pool_name" || {
        msg "RED" "添加 root 设备失败。"
        exit 1
    }

    msg "GREEN" "默认 profile 的根磁盘设备已设置为 '$pool_name'。"
}

delete_default_pool_if_exists() {
    if lxc storage list | grep -qw default; then
        msg "YELLOW" "检测到默认存储池 'default'，准备删除..."
        lxc storage delete default || {
            msg "RED" "删除默认存储池失败，请检查是否有正在使用该存储池的容器或 profile。"
            exit 1
        }
        msg "GREEN" "默认存储池 'default' 已成功删除。"
    fi
}

main() {
    check_root
    check_dependencies
    install_lxd
    create_btrfs_pool
    set_lxd_pool_as_default "btrfs-pool"
    delete_default_pool_if_exists
    msg "GREEN" "🎉 LXD 安装与配置已完成！"
}

main "$@"
