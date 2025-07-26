#!/bin/bash

# 确保 snap 的 lxc 可用
if ! command -v lxc >/dev/null 2>&1; then
  echo 'alias lxc="/snap/bin/lxc"' >> /root/.bashrc
  export PATH=$PATH:/snap/bin
  source /root/.bashrc
fi

#列出镜像列表
lxc image list