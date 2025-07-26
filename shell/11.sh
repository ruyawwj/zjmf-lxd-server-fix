#!/bin/bash

set -e

echo "请输入 zram 大小，数字部分（只允许正整数且不推荐超出真实内存大小）："
read -r size

# 验证数字是否合法（正整数）
if ! [[ "$size" =~ ^[0-9]+$ ]] || [ "$size" -le 0 ]; then
  echo "输入无效，必须是正整数数字。"
  exit 1
fi

echo "请选择单位，输入 M 或 G (不区分大小写)："
read -r unit

unit=$(echo "$unit" | tr '[:lower:]' '[:upper:]')

if [[ "$unit" != "M" && "$unit" != "G" ]]; then
  echo "单位输入错误，必须是 M 或 G。"
  exit 1
fi

# 拼接最终大小字符串
zram_size="${size}${unit}"

# 生成 systemd 服务文件内容
service_file="[Unit]
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
"

echo "生成的 systemd 服务文件内容如下："
echo "-----------------------------------"
echo "$service_file"
echo "-----------------------------------"

read -rp "是否写入到 /etc/systemd/system/zram-swap.service 并启用启动？ (Y/N): " yn
if [[ "$yn" =~ ^[Yy]$ ]]; then
  echo "$service_file" | sudo tee /etc/systemd/system/zram-swap.service > /dev/null
  echo "文件已写入。"

  echo "正在重新加载 systemd 配置..."
  sudo systemctl daemon-reload

  echo "正在启用 zram-swap 服务..."
  sudo systemctl enable zram-swap.service

  echo "正在启动/重启 zram-swap 服务..."
  sudo systemctl restart zram-swap.service

  echo "操作完成，zram-swap 服务已启用并启动。"
else
  echo "取消操作，未写入文件。"
fi
