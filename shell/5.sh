#!/bin/bash

# 检测当前是否存在 /swapfile 且正在使用
if swapon --show | grep -q '^/swapfile'; then
    echo "[INFO] 检测到系统已启用 /swapfile"
    read -rp "[?] 是否关闭当前的 /swapfile? [Y/N]: " confirm_close
    if [[ "$confirm_close" =~ ^[Yy]$ ]]; then
        echo "[INFO] 正在关闭 /swapfile..."
        swapoff /swapfile
        sed -i '/\/swapfile/d' /etc/fstab
        rm -f /swapfile
        echo "[INFO] /swapfile 已关闭"

        read -rp "[?] 是否需要创建新的 swap 文件? [Y/N]: " confirm_new
        if [[ "$confirm_new" =~ ^[Nn]$ ]]; then
            echo "[INFO] 已取消新建 swap，退出脚本。"
            exit 0
        fi
    else
        echo "[INFO] 已保留当前 /swapfile，退出脚本。"
        exit 0
    fi
fi

# 开始创建新的 swap
read -rp "[?] 请输入 swap 大小（纯数字）: " swap_size
read -rp "[?] 请输入单位（MB 或 GB）: " unit

# 转换为实际大小
case "$unit" in
    MB|mb)
        count=$swap_size
        ;;
    GB|gb)
        count=$((swap_size * 1024))
        ;;
    *)
        echo "[错误] 单位无效，仅支持 MB 或 GB"
        exit 1
        ;;
esac

echo "[INFO] 正在创建 ${swap_size}${unit} 的 swap 文件..."

# 创建 swap 文件
dd if=/dev/zero of=/swapfile bs=1M count=$count status=progress
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile

# 添加到 /etc/fstab
if ! grep -q '^/swapfile' /etc/fstab; then
    echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

echo "[INFO] swap 已创建并启用：$(free -h | grep Swap)"
