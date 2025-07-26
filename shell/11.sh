#!/bin/bash

set -e

# 去除输入字符串前后空白、回车换行符
trim_input() {
  echo "$1" | tr -d '\r\n' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//'
}

# 新增：检测旧服务文件是否存在
SERVICE_PATH="/etc/systemd/system/zram.service"
if [ -f "$SERVICE_PATH" ]; then
  echo "检测到已有 zram 服务文件：$SERVICE_PATH"
  read -rp "是否停止并删除旧服务，再继续？ (Y/N): " del_raw
  del=$(trim_input "$del_raw")
  if [[ "$del" =~ ^[Yy]$ ]]; then
    echo "停止旧服务..."
    sudo systemctl stop zram.service || true
    echo "禁用旧服务..."
    sudo systemctl disable zram.service || true
    echo "删除旧服务文件..."
    sudo rm -f "$SERVICE_PATH"
    echo "重新加载 systemd 配置..."
    sudo systemctl daemon-reload
    echo "旧服务已删除，继续执行。"
  else
    echo "未删除旧服务，脚本退出。"
    exit 0
  fi
fi

echo "请输入 zram 大小，数字部分（只允许正整数且不推荐超出真实内存大小）："
read -r size_raw
size=$(trim_input "$size_raw")

# 验证数字是否合法（正整数）
if ! [[ "$size" =~ ^[0-9]+$ ]] || [ "$size" -le 0 ]; then
  echo "输入无效，必须是正整数数字。"
  exit 1
fi

echo "请选择单位，输入 M 或 G (不区分大小写)："
read -r unit_raw
unit=$(trim_input "$unit_raw")
unit=$(echo "$unit" | tr '[:lower:]' '[:upper:]')

if [[ "$unit" != "M" && "$unit" != "G" ]]; then
  echo "单位输入错误，必须是 M 或 G。"
  exit 1
fi

zram_size="${size}${unit}"

echo "生成的 zram 大小为: $zram_size"

read -rp "是否写入到 $SERVICE_PATH 并启用启动？ (Y/N): " yn_raw
yn=$(trim_input "$yn_raw")

if [[ "$yn" =~ ^[Yy]$ ]]; then
  echo "写入服务文件..."
  sudo tee "$SERVICE_PATH" > /dev/null <<EOF
[Unit]
Description=Zram-based swap (compressed RAM block devices)

[Service]
Type=oneshot
ExecStartPre=/usr/sbin/modprobe zram
ExecStartPre=/usr/sbin/zramctl -s $zram_size /dev/zram0
ExecStartPre=/usr/sbin/mkswap /dev/zram0
ExecStart=/usr/sbin/swapon /dev/zram0
ExecStop=/usr/sbin/swapoff /dev/zram0
ExecStop=/usr/sbin/modprobe -r zram
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

  echo "重新加载 systemd 配置..."
  sudo systemctl daemon-reload

  echo "启用 zram 服务..."
  sudo systemctl enable zram.service

  echo "启动/重启 zram 服务..."
  sudo systemctl restart zram.service

  echo "显示 zram 服务状态："
  sudo systemctl status zram.service --no-pager

  echo "完成！"
else
  echo "取消操作。"
fi
