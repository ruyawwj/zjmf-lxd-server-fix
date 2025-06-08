计划：后端web管理+api文档。
本项目是为“魔方财务”系统开发的LXD服务器对接插件，允许通过魔方财务自动化开通、管理和销售LXD容器产品。

它由两部分组成：
1.  一个基于Python Flask的后端API服务器，负责与LXD进行交互，管理容器生命周期和网络。
2.  一个PHP插件，用于魔方财务系统，它与后端API通信，实现产品配置、自动化开通和客户前台管理功能。

## 后端API服务器 (`server/`)

后端服务是整个系统的核心，它提供了一套RESTful API接口，供魔方财务PHP插件或其他应用调用。

### 功能

* **API认证**: 所有API请求都通过HTTP头中的`apikey`进行身份验证。
* **容器管理**:
    * 创建、删除、启动、停止、重启容器。
    * 修改容器的root密码。
    * 重装容器系统。
* **资源监控**: 获取容器的实时资源使用情况，包括CPU、内存、硬盘和流量。
* **NAT管理**:
    * 使用`iptables`为容器添加和删除端口转发（NAT）规则。
    * 将NAT规则元数据持久化存储在`iptables_rules.json`文件中，确保可管理性。
    * 在创建和重装容器时，自动为SSH（22端口）添加一条随机的外部高位端口转发。

### 配置文件 (`app.ini`)

在首次启动前，您需要创建并配置`app.ini`文件。该文件包含了服务运行所需的所有重要参数。

```ini
[server]
# API服务监听的端口
HTTP_PORT = 8080
# 用于和PHP插件通信的API密钥，请务必修改为一个复杂的随机字符串
TOKEN = 7215EE9C7D9DC229D2921A40E899EC5F
# 日志级别，可选：DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_LEVEL = INFO

[lxc]
# 创建容器时使用的默认LXD镜像别名
DEFAULT_IMAGE_ALIAS = ubuntu-lts
# 容器连接的LXD网桥名称
NETWORK_BRIDGE = lxdbr0
# 容器使用的LXD存储池名称
STORAGE_POOL = default
# 容器内用于修改密码的默认用户名
DEFAULT_CONTAINER_USER = root
# 宿主机用于NAT MASQUERADE规则的主网卡名称 (例如 eth0, enp4s0)
MAIN_INTERFACE = enp0s6
# 宿主机上用于监听NAT转发的公网IP地址
NAT_LISTEN_IP = 10.0.0.210
```

### 安装与启动

1.  进入`server`目录。
2.  安装所需的Python依赖包：
    ```bash
    pip install -r requirements.txt
    ```
3.  根据您的服务器环境，正确配置`app.ini`文件。
4.  由于API需要执行`iptables`命令来管理网络规则，您需要确保运行此应用的用户拥有无密码执行`sudo iptables`的权限。可以通过编辑`sudoers`文件实现：
    ```
    # 将 "your_user" 替换为实际运行应用的用户名
    your_user ALL=(ALL) NOPASSWD: /usr/sbin/iptables
    ```
5.  启动API服务器：
    ```bash
    python app.py
    ```
    在生产环境中，强烈建议使用Gunicorn或uWSGI等专业的WSGI服务器来运行，并配置为系统服务。

## 魔方财务PHP插件 (`lxdserver/`)

此插件作为魔方财务与后端API服务器之间的桥梁。

### 功能

* **服务器对接**: 在魔方后台可测试与后端API的连接状态和API密钥的有效性。
* **产品配置**: 提供了丰富的产品可配置选项，如CPU核心数、内存、硬盘、带宽、流量和端口转发数量限制等。
* **自动化开通**: 自动调用后端API完成`Create`、`Terminate`、`Suspend`、`Unsuspend`等操作。
* **客户前台**:
    * **产品信息**: 以卡片和进度条的形式直观展示容器的资源使用情况。
    * **NAT转发**: 允许客户在管理员设定的数量限制内，自助添加和删除端口转发规则。
    * **电源管理**: 开机、关机、重启。
    * **密码重置**: 客户可自助重置容器的root密码。
    * **系统重装**: 客户可自助重装系统。

### 安装与配置

1.  将`lxdserver`整个目录上传到您的魔方财务网站的 `/modules/servers/` 目录下。
2.  登录您的魔方财务管理员后台，进入“产品管理” -> “接口管理”。
3.  点击“新增接口”，然后填写以下信息：
    * **接口名称**: 自定义，例如 “我的LXD服务器”。
    * **接口类型**: 在下拉菜单中选择“魔方财务-LXD对接插件 by xkatld”。
    * **服务器IP**: 填写您后端API服务器的IP地址。
    * **端口**: 填写您在`app.ini`中配置的`HTTP_PORT`。
    * **接口密码**: 填写您在`app.ini`中配置的`TOKEN`。
4.  保存并点击“测试连接”，如果提示“LXD API服务器连接成功且API密钥有效”，则表示配置成功。
5.  现在，您可以在“产品管理” -> “产品列表”中创建或编辑产品，在“模块设置”标签页下选择刚刚配置好的LXD接口，并根据需求设置各项产品参数。
