#!/bin/bash

# 镜像信息
IMAGE_URL="https://lsez.site/f/3OCL/debian12-arm64-ssh.tar.gz"
IMAGE_FILE="debian12-arm64-ssh.tar.gz"
ALIAS_NAME="debian12-arm64-ssh"

# 1. 检查 LXD 是否已安装
if ! command -v lxc >/dev/null 2>&1; then
    echo "错误：未安装 lxc 命令。请先安装 LXD。"
    exit 1
fi

# 2. 下载镜像
echo "[1/5] 正在下载镜像..."
curl -L -o "$IMAGE_FILE" "$IMAGE_URL"
if [ $? -ne 0 ]; then
    echo "错误：镜像下载失败。"
    exit 1
fi

# 3. 尝试导入镜像，捕获 fingerprint
echo "[2/5] 尝试导入镜像以获取 fingerprint..."
IMPORT_OUTPUT=$(lxc image import "$IMAGE_FILE" --alias "$ALIAS_NAME" 2>&1)

# 如果导入成功
if echo "$IMPORT_OUTPUT" | grep -q "Image imported with fingerprint:"; then
    echo "[3/5] 导入成功。"
    echo "$IMPORT_OUTPUT"
    rm -f "$IMAGE_FILE"
    exit 0
fi

# 如果 fingerprint 已存在导致失败
if echo "$IMPORT_OUTPUT" | grep -q "Image with same fingerprint already exists"; then
    echo "[3/5] 镜像 fingerprint 已存在，正在处理..."

    # 获取已存在镜像的 fingerprint（根据文件的 SHA256）
    IMAGE_FP=$(sha256sum "$IMAGE_FILE" | awk '{print $1}')

    # 检查是否已存在指定 alias
    EXISTING_ALIAS=$(lxc image list --format csv | grep "$IMAGE_FP" | grep "$ALIAS_NAME")

    if [ -n "$EXISTING_ALIAS" ]; then
        echo "[4/5] 镜像已存在，alias 也已存在，无需导入。"
    else
        echo "[4/5] 镜像已存在，但 alias 缺失，正在创建 alias..."
        lxc image alias create "$ALIAS_NAME" "$IMAGE_FP"
    fi

    echo "[5/5] 已完成处理。"
    rm -f "$IMAGE_FILE"
    exit 0
fi

# 如果导入失败但不是 fingerprint 冲突
echo "错误：镜像导入失败。详细信息如下："
echo "$IMPORT_OUTPUT"
rm -f "$IMAGE_FILE"
exit 1
