#!/bin/bash

echo "系统中可能缺少可用的 'lxc' 命令。"
echo
echo "请手动执行以下命令以添加 alias 并设置 PATH："
echo
echo "--------------------------------------------"
echo '! lxc -h >/dev/null 2>&1 && echo '\''alias lxc="/snap/bin/lxc"'\'' >> /root/.bashrc && source /root/.bashrc'
echo 'export PATH=$PATH:/snap/bin'
echo "--------------------------------------------"
echo
echo "执行完以上命令后，再次运行此脚本执行中断选项即可。"
exit 1