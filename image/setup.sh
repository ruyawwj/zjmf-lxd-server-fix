#!/bin/bash

if [ "$(id -u)" -ne 0 ]; then
   echo "错误：此脚本必须以root用户身份运行。"
   echo "请尝试使用 'sudo bash' 命令来执行。"
   exit 1
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
            echo "安装 $1 失败，请手动安装后重试。"
            exit 1
        fi
    fi
}

check_and_install wget
check_and_install unzip

clear
echo "============================================="
echo "      欢迎使用 LXC 镜像部署脚本"
echo "============================================="
echo
echo "请选择您的设备架构:"
echo "  1) arm64"
echo "  2) amd64"
echo
read -p "请输入选项 [1-2]: " choice

case $choice in
    1)
        ARCH="arm64"
        URL="https://lsez.site/f/5zi0/lxc_image_backups_20250611_032142.zip"
        FILENAME="lxc_image_backups_arm64.zip"
        ;;
    2)
        ARCH="amd64"
        URL="https://lsez.site/f/z4FK/lxc_image_backups_20250611_031849.zip"
        FILENAME="lxc_image_backups_amd64.zip"
        ;;
    *)
        echo "错误：无效的选项，脚本已退出。"
        exit 1
        ;;
esac

DEST_DIR="/root/lxc_image_backups/"

echo "您已选择: ${ARCH}"
echo
echo "步骤 1/4: 开始下载文件..."
wget --progress=bar:force -O ${FILENAME} ${URL}
if [ $? -ne 0 ]; then
    echo "错误：下载失败，请检查您的网络连接或URL是否正确。"
    exit 1
fi
echo "下载完成。"
echo

echo "步骤 2/4: 创建并解压文件到 ${DEST_DIR}..."
mkdir -p ${DEST_DIR}
unzip -o ${FILENAME} -d ${DEST_DIR}
if [ $? -ne 0 ]; then
    echo "错误：解压失败，文件可能已损坏。"
    rm -f ${FILENAME}
    exit 1
fi
rm -f ${FILENAME}
echo "解压完成。"
echo

echo "步骤 3/4: 下载管理脚本..."
wget -O lxd-helper.sh https://raw.githubusercontent.com/xkatld/LinuxTools/refs/heads/main/shell/lxd-helper.sh
if [ $? -ne 0 ]; then
    echo "错误：下载 lxd-helper.sh 失败。"
    exit 1
fi
echo "下载完成。"
echo

echo "步骤 4/4: 运行管理脚本..."
echo "============================================="
chmod +x lxd-helper.sh
./lxd-helper.sh

echo "============================================="
echo "所有操作已执行完毕。"
