#!/bin/bash

IMAGE_URL="https://lsez.site/f/3OCL/debian12-arm64-ssh.tar.gz"
IMAGE_FILE="debian12-arm64-ssh.tar.gz"
ALIAS_NAME="debian12-arm64-ssh"

if ! command -v lxc >/dev/null 2>&1; then
    echo "LXD (lxc) 未安装，请先安装 LXD。" >&2
    exit 1
fi

echo "正在下载镜像..."
curl -L -o "$IMAGE_FILE" "$IMAGE_URL"
if [ $? -ne 0 ]; then
    echo "镜像下载失败，请检查 URL 是否正确。"
    exit 1
fi

echo "检查镜像是否已存在..."
FINGERPRINT=$(tar -O -xf "$IMAGE_FILE" metadata.yaml | grep '^fingerprint:' | awk '{print $2}')
if lxc image list | grep -q "$FINGERPRINT"; then
    echo "镜像已存在 fingerprint: $FINGERPRINT"
    read -p "是否删除已有镜像并覆盖？(y/N): " confirm
    if [[ "$confirm" =~ ^[Yy]$ ]]; then
        lxc image delete "$FINGERPRINT"
    else
        echo "已取消导入。"
        exit 0
    fi
fi

echo "正在导入镜像..."
lxc image import "$IMAGE_FILE" --alias "$ALIAS_NAME"
if [ $? -eq 0 ]; then
    echo "镜像导入成功，别名为：$ALIAS_NAME"
else
    echo "镜像导入失败。"
    exit 1
fi
