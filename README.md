



# 此模块由Python进行编写



-----



# 魔方财务-LXD 对接插件 (zjmf-lxd-server)

这是一个为 [魔方财务](https://www.idcsmart.com/) (ZJMF) 系统开发的 LXD 对接插件，旨在为主机商提供一套完整、自动化的 LXD 容器销售与管理解决方案。

项目通过一个独立的后端服务与魔方财务插件相结合的模式，实现了高效、安全、功能丰富的 LXD 容器管理体验。

**详细的使用文档，请参考 [项目 Wiki](https://github.com/ruyawwj/zjmf-lxd-server-fix/wiki/%E4%BD%BF%E7%94%A8%E5%B8%AE%E5%8A%A9)，安装使用如下指令按顺序执行即可，**

本人为此项目创建了一键脚本 下面是一键指令,执行前请先执行
```
apt install curl wget bash -y
```
一键指令：
```
bash <(curl -sSL https://raw.githubusercontent.com/ruyawwj/zjmf-lxd-server-fix/refs/heads/main/install.sh)
```
或者
```
curl -sSL https://raw.githubusercontent.com/ruyawwj/zjmf-lxd-server-fix/refs/heads/main/install.sh | bash
```

-----

## 核心功能

  * **自动化供应**：通过魔方财务自动创建、终止、暂停和恢复 LXD 容器，支持重装系统和重置密码功能。
  * **资源配置**：在魔方财务产品设置中灵活配置容器资源，包括 CPU 核心数、内存、硬盘大小、网络带宽和流量限制。
  * **客户端功能**：客户可在魔方财务的用户中心查看容器的实时状态、管理 NAT 转发规则。
  * **Web 管理面板**：后端服务自带一个独立的 Web 管理界面，用于集中监控和管理所有创建的 LXD 容器，并提供快捷操作。
  * **安全隔离**：通过独立的 Python API 服务器 和 Token 认证机制，将 LXD 主机与魔方财务面板有效隔离，增强安全性。

-----

## 项目截图

![image](https://github.com/user-attachments/assets/39fe815e-b1e2-449b-a6a6-1a9206aa7497)

![image](https://github.com/user-attachments/assets/659ccc24-d213-47bc-8b7d-89c18a93165e)

![image](https://github.com/user-attachments/assets/10db6034-7d85-44a1-b021-e3e87ea9a2e8)

![image](https://github.com/user-attachments/assets/f8311d1d-bcdc-4eed-bfd9-90bb69afa2d3)

![image](https://github.com/user-attachments/assets/951ea9a4-ffe3-46dd-8231-589dd725bf2a)

![image](https://github.com/user-attachments/assets/01e53d28-54fe-40be-9bb7-833cc361eb58)
