# Senkin LXC Controller (Open Source)

一个用于管理LXC容器的Python Flask应用，旨在与Senkin LXC类IDC面板插件交互。

## 安装

1.  克隆或下载此项目。
2.  安装Python 3.x。
3.  安装LXD并确保其正常运行。当前用户需要有权限访问LXD (通常通过加入 `lxd` 用户组)。
4.  安装依赖:
    ```bash
    pip install -r requirements.txt
    ```
5.  配置Apache2 (如果使用域名绑定功能):
    * 确保 `mod_proxy` 和 `mod_proxy_http` 已启用:
        ```bash
        sudo a2enmod proxy proxy_http
        sudo systemctl restart apache2
        ```
    * 确保运行此Flask应用的用户有权限执行 `app.ini` 中定义的Apache相关命令 (例如 `a2ensite`, `a2dissite`, `systemctl reload apache2`)。这通常通过配置无密码 `sudo` 实现，例如在 `/etc/sudoers.d/senkinlxc_controller` 文件中添加:
        ```
        your_flask_user ALL=(ALL) NOPASSWD: /usr/sbin/a2ensite
        your_flask_user ALL=(ALL) NOPASSWD: /usr/sbin/a2dissite
        your_flask_user ALL=(ALL) NOPASSWD: /bin/systemctl reload apache2
        ```
        请将 `your_flask_user`替换为实际运行Flask应用的用户。**注意：配置sudo权限时务必谨慎，并确保路径准确无误。**

## 配置

1.  复制或重命名 `app.ini.example` (如果提供) 为 `app.ini`。
2.  编辑 `app.ini` 并填入您的配置信息，特别是 `[server]` 部分的 `TOKEN` 和 `[apache]` 部分的命令路径。

## 运行

```bash
python app.py
```

应用将在 `app.ini` 中配置的端口上监听。

## API认证

所有API请求都需要在HTTP头部包含 `apikey` 字段，其值为 `app.ini` 中配置的 `TOKEN`。

## 注意事项

* **域名绑定**: `list_domain_bindings` 功能当前返回所有由 `apache_manager` 管理的域名。为了精确地按容器列出域名，需要改进域名与容器的关联逻辑（例如，在创建绑定时将容器名存储在vHost配置的注释中，或使用外部元数据存储）。
* **流量统计**: `getinfo` 中的流量统计是基于LXD网络接口计数器的累计值，不会按月重置。
* **NAT和域名数量限制**: 已在创建容器时将限制值存入LXD容器的 `user.*` 配置中。`addport` API会检查NAT限制，但`adddomain`由于`list_domain_bindings`的当前局限性，其限制检查可能不准确。
```

**后续步骤和改进点：**

* **域名与容器的精确关联**: 这是 `list_domain_bindings` 和相关限制检查的关键。
* **流量按周期统计/重置**: 需要外部任务或更复杂的逻辑。
* **更细致的错误码和消息**: 可以根据具体失败原因返回更详细的错误信息。
* **异步任务处理**: 对于耗时操作（如创建、重装），可以考虑使用任务队列（如Celery）以避免请求超时。
* **安全性**: 对所有输入进行严格校验。进一步审查`sudo`权限的必要性和范围。
