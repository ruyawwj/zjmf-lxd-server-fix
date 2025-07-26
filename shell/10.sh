#!/bin/bash

set -e

# 确保 snap 的 lxc 可用
if ! command -v lxc >/dev/null 2>&1; then
  echo 'alias lxc="/snap/bin/lxc"' >> /root/.bashrc
  export PATH=$PATH:/snap/bin
  source /root/.bashrc
fi

INI_FILE="/root/zjmf-lxd-server-fix/server/app.ini"
SECTION="lxc"
KEY="DEFAULT_IMAGE_ALIAS"

echo "当前可用镜像列表："
lxc image list
echo

while true; do
  read -p "请输入 DEFAULT_IMAGE_ALIAS 的镜像别名（例如 debian-11-amd64）: " user_input
  if [ -z "$user_input" ]; then
    echo "输入不能为空，请重新输入。"
  else
    break
  fi
done

# 替换 app.ini 中 [lxc] 段内的 DEFAULT_IMAGE_ALIAS
if grep -q "^\s*${KEY}\s*=" "$INI_FILE"; then
  sed -i "/^\[${SECTION}\]/, /^\[/ s|^\s*${KEY}\s*=.*|${KEY} = ${user_input}|" "$INI_FILE"
else
  sed -i "/^\[${SECTION}\]/,/^\[/ {
    /^\[/! {
      \$a${KEY} = ${user_input}
    }
  }" "$INI_FILE"
fi

echo "已更新 $INI_FILE 中的 $KEY 为: $user_input"
exit 0
