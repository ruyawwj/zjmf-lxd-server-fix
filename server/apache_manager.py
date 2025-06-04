import os
import subprocess
from config_handler import app_config

def _run_shell_command(command):
    try:
        process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = process.communicate()
        if process.returncode != 0:
            error_message = stderr.decode('utf-8', errors='ignore').strip()
            return False, f"命令执行失败: {error_message}"
        return True, stdout.decode('utf-8', errors='ignore').strip()
    except Exception as e:
        return False, f"执行命令时发生异常: {str(e)}"

def _get_vhost_filename(domain):
    return f"{domain}{app_config.apache_config_suffix}"

def _get_vhost_filepath(domain):
    return os.path.join(app_config.managed_vhost_dir, _get_vhost_filename(domain))

def create_apache_vhost(domain, container_ip, container_port=None):
    if not all([app_config.managed_vhost_dir, app_config.a2ensite_command, app_config.web_server_reload_command]):
        return False, "Apache管理未完全配置"

    target_port = container_port or app_config.default_proxy_port
    vhost_content = f"""<VirtualHost *:80>
    ServerName {domain}
    ProxyPreserveHost On
    ProxyPass / http://{container_ip}:{target_port}/
    ProxyPassReverse / http://{container_ip}:{target_port}/
    ErrorLog ${{APACHE_LOG_DIR}}/{domain}-error.log
    CustomLog ${{APACHE_LOG_DIR}}/{domain}-access.log combined
</VirtualHost>
"""
    filepath = _get_vhost_filepath(domain)
    try:
        with open(filepath, 'w') as f:
            f.write(vhost_content)
        
        success, msg = _run_shell_command(f"{app_config.a2ensite_command} {_get_vhost_filename(domain)}")
        if not success:
            os.remove(filepath) 
            return False, f"启用站点失败: {msg}"
        
        success, msg = _run_shell_command(app_config.web_server_reload_command)
        if not success:
            _run_shell_command(f"{app_config.a2dissite_command} {_get_vhost_filename(domain)}")
            os.remove(filepath)
            return False, f"重载Apache失败: {msg}"
            
        return True, "域名绑定成功创建并启用"
    except IOError as e:
        return False, f"写入虚拟主机文件失败: {str(e)}"
    except Exception as e:
        if os.path.exists(filepath):
            os.remove(filepath)
        return False, f"创建虚拟主机时发生未知错误: {str(e)}"

def delete_apache_vhost(domain):
    if not all([app_config.managed_vhost_dir, app_config.a2dissite_command, app_config.web_server_reload_command]):
        return False, "Apache管理未完全配置"

    filepath = _get_vhost_filepath(domain)
    if not os.path.exists(filepath):
        return False, "域名绑定配置不存在"

    success, msg = _run_shell_command(f"{app_config.a2dissite_command} {_get_vhost_filename(domain)}")
    if not success:
        return False, f"禁用站点失败: {msg}"
    
    try:
        os.remove(filepath)
    except OSError as e:
        _run_shell_command(f"{app_config.a2ensite_command} {_get_vhost_filename(domain)}")
        return False, f"删除虚拟主机文件失败: {str(e)}"

    success, msg = _run_shell_command(app_config.web_server_reload_command)
    if not success:
        return False, f"重载Apache失败: {msg}"
        
    return True, "域名绑定成功删除"

def list_apache_bindings():
    if not app_config.managed_vhost_dir:
        return []
    bindings = []
    try:
        for filename in os.listdir(app_config.managed_vhost_dir):
            if filename.endswith(app_config.apache_config_suffix):
                domain = filename[:-len(app_config.apache_config_suffix)]
                bindings.append({'Domain': domain})
    except FileNotFoundError:
        return []
    except Exception:
        return []
    return bindings
