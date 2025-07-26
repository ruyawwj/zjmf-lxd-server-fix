#!/bin/bash

if [ "$(id -u)" -ne 0 ]; then
   echo "错误：此脚本必须以root用户身份运行。"
   echo "请尝试使用 'sudo bash' 命令来执行。"
   exit 1
fi

# 设置 snap 路径和 alias，避免 lxc 命令未找到
if ! lxc -h >/dev/null 2>&1; then
    export PATH=$PATH:/snap/bin
    echo 'export PATH=$PATH:/snap/bin' >> /root/.bashrc

    if [ -x /snap/bin/lxc ]; then
        echo 'alias lxc="/snap/bin/lxc"' >> /root/.bashrc
        alias lxc="/snap/bin/lxc"
        echo "已设置 alias，使 lxc 指向 /snap/bin/lxc"
    fi
fi

check_and_install() {
    if ! command -v $1 &> /dev/null; then
        echo "$1 未安装，正在尝试安装..."
        if command -v apt-get &> /dev/null; then
            apt-get update >/dev/null 2>&1 && apt-get install -y $1 >/dev/null 2>&1
        elif command -v yum &> /dev/null; then
            yum install -y $1 >/dev/null 2>&1
        elif command -v dnf &> /dev/null; then
            dnf install -y $1 >/dev/null 2>&1
        else
            echo "无法确定包管理器，请手动安装 $1 后再运行脚本。"
            exit 1
        fi
        if ! command -v $1 &> /dev/null; then
            echo "安装 $1 失败，请手动安装后重试。(LXC安装指令:export PATH=$PATH:/snap/bin && alias lxc="/snap/bin/lxc" && echo 'export PATH=$PATH:/snap/bin' >> /root/.bashrc && echo 'alias lxc="/snap/bin/lxc"' >> /root/.bashrc
)"
            exit 1
        fi
    fi
}

check_and_install wget
check_and_install lxc

MACHINE_ARCH=$(uname -m)
case "$MACHINE_ARCH" in
    x86_64)
        ARCH="amd64"
        ;;
    aarch64|arm64)
        ARCH="arm64"
        ;;
    *)
        echo "不支持的系统架构：$MACHINE_ARCH"
        exit 1
        ;;
esac

DEST_DIR="/root/image"
mkdir -p "${DEST_DIR}"

while true; do
    clear
    echo "============================================="
    echo "      欢迎使用 LXC 镜像部署脚本"
    echo "============================================="
    echo
    echo "当前检测架构: $ARCH"
    echo
    echo "请选择要部署的系统镜像:"
    echo "  1) Debian"
    echo "  2) Ubuntu"
    echo "  3) CentOS"
    echo "  4) AlmaLinux"
    echo "  5) Fedora"
    echo "  6) openSUSE"
    echo "  7) RockyLinux"
    echo "  0) 退出"
    echo
    read -p "请输入选项 [0-7]: " os_choice

    if [ "$os_choice" == "0" ]; then
        echo "退出脚本。"
        exit 0
    fi

    case $os_choice in
        1)
            OS="debian"
            echo "请选择 Debian 版本:"
            echo "  1) 11"
            echo "  2) 12"
            echo "  3) 13"
            read -p "请输入选项 [1-3]: " ver_choice
            case $ver_choice in
                1) VERSION="11" ;;
                2) VERSION="12" ;;
                3) VERSION="13" ;;
                *) echo "无效选项，返回主菜单。"; read -p "按回车继续..." ; continue ;;
            esac
            ;;
        2)
            OS="ubuntu"
            echo "请选择 Ubuntu 版本:"
            echo "  1) 20.04"
            echo "  2) 22.04"
            echo "  3) 24.10"
            echo "  4) 25.04"
            read -p "请输入选项 [1-4]: " ver_choice
            case $ver_choice in
                1) VERSION="20-04" ;;
                2) VERSION="22-04" ;;
                3) VERSION="24-10" ;;
                4) VERSION="25-04" ;;
                *) echo "无效选项，返回主菜单。"; read -p "按回车继续..." ; continue ;;
            esac
            ;;
        3)
            OS="centos"
            echo "CentOS 仅支持以下版本："
            echo "  1) CentOS Stream 9"
            read -p "请输入选项 [1]: " ver_choice
            case $ver_choice in
                1) VERSION="9-stream" ;;
                *) echo "无效选项，返回主菜单。"; read -p "按回车继续..." ; continue ;;
            esac
            ;;
        4)
            OS="almalinux"
            echo "请选择 AlmaLinux 版本:"
            echo "  1) 8"
            echo "  2) 9"
            read -p "请输入选项 [1-2]: " ver_choice
            case $ver_choice in
                1) VERSION="8" ;;
                2) VERSION="9" ;;
                *) echo "无效选项，返回主菜单。"; read -p "按回车继续..." ; continue ;;
            esac
            ;;
        5)
            OS="fedora"
            echo "请选择 Fedora 版本:"
            echo "  1) 40"
            echo "  2) 41"
            echo "  3) 42"
            read -p "请输入选项 [1-3]: " ver_choice
            case $ver_choice in
                1) VERSION="40" ;;
                2) VERSION="41" ;;
                3) VERSION="42" ;;
                *) echo "无效选项，返回主菜单。"; read -p "按回车继续..." ; continue ;;
            esac
            ;;
        6)
            OS="opensuse"
            echo "请选择 openSUSE 版本:"
            echo "  1) 15.5"
            echo "  2) 15.6"
            echo "  3) tumbleweed"
            read -p "请输入选项 [1-3]: " ver_choice
            case $ver_choice in
                1) VERSION="15-5" ;;
                2) VERSION="15-6" ;;
                3) VERSION="tumbleweed" ;;
                *) echo "无效选项，返回主菜单。"; read -p "按回车继续..." ; continue ;;
            esac
            ;;
        7)
            OS="rockylinux"
            echo "请选择 RockyLinux 版本:"
            echo "  1) 8"
            echo "  2) 9"
            read -p "请输入选项 [1-2]: " ver_choice
            case $ver_choice in
                1) VERSION="8" ;;
                2) VERSION="9" ;;
                *) echo "无效选项，返回主菜单。"; read -p "按回车继续..." ; continue ;;
            esac
            ;;
        *)
            echo "无效选项，返回主菜单。"
            read -p "按回车继续..."
            continue
            ;;
    esac

    if [ "$ARCH" == "arm64" ]; then
        case "${OS}_${VERSION}" in
            centos_9-stream)      FILENAME="centos9-stream-arm64-ssh.tar.gz" ;;
            debian_11)            FILENAME="debian11-arm64-ssh.tar.gz" ;;
            debian_12)            FILENAME="debian12-arm64-ssh.tar.gz" ;;
            debian_13)            FILENAME="debian13-arm64-ssh.tar.gz" ;;
            ubuntu_20-04)         FILENAME="ubuntu20-04-arm64-ssh.tar.gz" ;;
            ubuntu_22-04)         FILENAME="ubuntu22-04-arm64-ssh.tar.gz" ;;
            ubuntu_24-10)         FILENAME="ubuntu24-10-arm64-ssh.tar.gz" ;;
            ubuntu_25-04)         FILENAME="ubuntu25-04-arm64-ssh.tar.gz" ;;
            almalinux_8)          FILENAME="almalinux8-arm64-ssh.tar.gz" ;;
            almalinux_9)          FILENAME="almalinux9-arm64-ssh.tar.gz" ;;
            fedora_40)            FILENAME="fedora40-arm64-ssh.tar.gz" ;;
            fedora_41)            FILENAME="fedora41-arm64-ssh.tar.gz" ;;
            fedora_42)            FILENAME="fedora42-arm64-ssh.tar.gz" ;;
            opensuse_15-5)        FILENAME="opensuse15-5-arm64-ssh.tar.gz" ;;
            opensuse_15-6)        FILENAME="opensuse15-6-arm64-ssh.tar.gz" ;;
            opensuse_tumbleweed)  FILENAME="opensusetumbleweed-arm64-ssh.tar.gz" ;;
            rockylinux_8)         FILENAME="rockylinux8-arm64-ssh.tar.gz" ;;
            rockylinux_9)         FILENAME="rockylinux9-arm64-ssh.tar.gz" ;;
            *)
                echo "错误：不支持的 arm64 系统版本组合 ${OS}_${VERSION}"
                read -p "按回车返回主菜单..."
                continue
                ;;
        esac
        URL="https://github.com/StarVM-OpenSource/zjmf-lxd-server-fix/releases/download/arm64/${FILENAME}"
    elif [ "$ARCH" == "amd64" ]; then
        case "${OS}_${VERSION}" in
            centos_9-stream)      FILENAME="centos9-stream-amd64-ssh.tar.gz" ;;
            debian_11)            FILENAME="debian11-amd64-ssh.tar.gz" ;;
            debian_12)            FILENAME="debian12-amd64-ssh.tar.gz" ;;
            debian_13)            FILENAME="debian13-amd64-ssh.tar.gz" ;;
            ubuntu_20-04)         FILENAME="ubuntu20-04-amd64-ssh.tar.gz" ;;
            ubuntu_22-04)         FILENAME="ubuntu22-04-amd64-ssh.tar.gz" ;;
            ubuntu_24-10)         FILENAME="ubuntu24-10-amd64-ssh.tar.gz" ;;
            ubuntu_25-04)         FILENAME="ubuntu25-04-amd64-ssh.tar.gz" ;;
            almalinux_8)          FILENAME="almalinux8-amd64-ssh.tar.gz" ;;
            almalinux_9)          FILENAME="almalinux9-amd64-ssh.tar.gz" ;;
            fedora_40)            FILENAME="fedora40-amd64-ssh.tar.gz" ;;
            fedora_41)            FILENAME="fedora41-amd64-ssh.tar.gz" ;;
            fedora_42)            FILENAME="fedora42-amd64-ssh.tar.gz" ;;
            opensuse_15-5)        FILENAME="opensuse15-5-amd64-ssh.tar.gz" ;;
            opensuse_15-6)        FILENAME="opensuse15-6-amd64-ssh.tar.gz" ;;
            opensuse_tumbleweed)  FILENAME="opensusetumbleweed-amd64-ssh.tar.gz" ;;
            rockylinux_8)         FILENAME="rockylinux8-amd64-ssh.tar.gz" ;;
            rockylinux_9)         FILENAME="rockylinux9-amd64-ssh.tar.gz" ;;
            *)
                echo "错误：不支持的 amd64 系统版本组合 ${OS}_${VERSION}"
                read -p "按回车返回主菜单..."
                continue
                ;;
        esac
        URL="https://github.com/StarVM-OpenSource/zjmf-lxd-server-fix/releases/download/amd64/${FILENAME}"
    else
        echo "错误：未知架构。"
        read -p "按回车返回主菜单..."
        continue
    fi

    echo
    echo "您已选择: ${OS} ${VERSION} - 架构 ${ARCH}"
    echo "步骤 1/2: 开始下载文件..."
    wget --progress=bar:force -O "${DEST_DIR}/${FILENAME}" "${URL}"
    if [ $? -ne 0 ]; then
        echo "错误：下载失败，请检查网络或链接有效性。"
        read -p "按回车返回主菜单..."
        continue
    fi
    echo "下载完成。"
    echo

    echo "步骤 2/2: 导入 LXC 镜像..."
    lxc image import "${DEST_DIR}/${FILENAME}" --alias "${OS}-${VERSION}-${ARCH}"
    if [ $? -ne 0 ]; then
        echo "错误：导入 LXC 镜像失败。"
        read -p "按回车返回主菜单..."
        continue
    fi
    rm -f "${DEST_DIR:?}/${FILENAME}"
    echo "镜像导入成功。"
    echo

    echo "按回车返回主菜单，继续选择其它镜像..."
    read -r
done
