#!/bin/bash

set -e

IMAGE_URL="https://lsez.site/f/3OCL/debian12-arm64-ssh.tar.gz"
IMAGE_FILE="debian12-arm64-ssh.tar.gz"
ALIAS_NAME="debian12-arm64-ssh"

echo "[信息] 开始执行精简版安装脚本..."

echo "[步骤 1/4] 清理旧的下载文件 (如果存在)..."
rm -f "$IMAGE_FILE"

echo "[步骤 2/4] 清理旧的LXD镜像 (如果存在)..."
lxc image delete "$ALIAS_NAME" >/dev/null 2>&1 || true

echo "[步骤 3/4] 使用 wget 强制下载新镜像..."
wget -O "$IMAGE_FILE" "$IMAGE_URL"

echo "[步骤 4/4] 直接导入LXD..."
lxc image import "$IMAGE_FILE" --alias "$ALIAS_NAME"

echo "[成功] 操作完成。"

rm -f "$IMAGE_FILE"
