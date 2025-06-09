#!/bin/bash

# 镜像地址和设置
IMAGE_URL="https://lsez.site/f/3OCL/debian12-arm64-ssh.tar.gz"
IMAGE_FILE="debian12-arm64-ssh.tar.gz"
ALIAS_NAME="debian12-arm64-ssh"

# 检查 lxc 是否可用
if ! command -v lxc >/dev/null 2>&1; then
    echo "错误：未找到 lxc 命令，请先安装 LXD。"
    exit 1
fi

# 下载镜像
echo "[1/4] 下载镜像..."
curl -L -o "$IMAGE_FILE" "$IMAGE_URL"
if [ $? -ne 0 ]; then
    echo "错误：镜像下载失败。"
    exit 1
fi

# 检查是否已有相同 alias 的镜像
echo "[2/4] 检查是否已存在别名为 '$ALIAS_NAME' 的镜像..."
if lxc image list --format csv | grep -q ",$ALIAS_NAME,"; then
    echo "提示：镜像别名 '$ALIAS_NAME' 已存在。"
    read -p "是否删除已存在镜像并重新导入？(y/N): " confirm
    if [[ "$confirm" =~ ^[Yy]$ ]]; then
        echo "删除已存在镜像..."
        IMAGE_ID=$(lxc image list --format csv | grep ",$ALIAS_NAME," | cut -d',' -f1)
        lxc image delete "$IMAGE_ID"
    else
        echo "已取消导入操作。"
        rm -f "$IMAGE_FILE"
        exit 0
    fi
fi

# 导入镜像
echo "[3/4] 正在导入镜像..."
lxc image import "$IMAGE_FILE" --alias "$ALIAS_NAME"
if [ $? -ne 0 ]; then
    echo "错误：镜像导入失败。"
    rm -f "$IMAGE_FILE"
    exit 1
fi

echo "[4/4] 导入成功，镜像别名为：$ALIAS_NAME"

# 可选：删除本地镜像文件
# rm -f "$IMAGE_FILE"
