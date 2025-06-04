import configparser
import os
from functools import wraps
from flask import Flask, request, jsonify
from pylxd import Client as LXDClient
from pylxd.exceptions import LXDAPIException, NotFound

app = Flask(__name__)

CONFIG_FILE = 'app.ini'

def load_config():
    config = configparser.ConfigParser()
    if not os.path.exists(CONFIG_FILE):
        raise RuntimeError(f"配置文件 {CONFIG_FILE} 未找到")
    config.read(CONFIG_FILE)
    app_config = {}
    try:
        app_config['HTTP_PORT'] = config.getint('server', 'HTTP_PORT', fallback=8080)
        app_config['TOKEN'] = config.get('server', 'TOKEN')
        app_config['DEFAULT_IMAGE'] = config.get('lxc', 'DEFAULT_IMAGE', fallback='images:alpine/edge')
        app_config['NET_INTERFACE'] = config.get('lxc', 'NET_INTERFACE', fallback='lxdbr0')
        app_config['MAIN_INTERFACE'] = config.get('lxc', 'MAIN_INTERFACE', fallback='eth0')
        app_config['IP_PREFIX'] = config.get('lxc', 'IP_PREFIX', fallback='10.0.3')
        app_config['STORAGE_POOL'] = config.get('lxc', 'STORAGE_POOL', fallback='default')
    except (configparser.NoSectionError, configparser.NoOptionError) as e:
        raise RuntimeError(f"配置文件错误: {e}")
    if not app_config['TOKEN']:
        raise RuntimeError("配置文件中必须设置API TOKEN")
    return app_config

config = load_config()
lxd_client = LXDClient()

def api_key_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if request.headers.get('apikey') and request.headers.get('apikey') == config['TOKEN']:
            return f(*args, **kwargs)
        else:
            return jsonify({'code': 401, 'msg': '认证失败或API密钥无效'}), 401
    return decorated_function

def get_container_or_404(hostname):
    try:
        return lxd_client.containers.get(hostname)
    except NotFound:
        return None
    except LXDAPIException as e:
        app.logger.error(f"获取容器 {hostname} 时发生LXD API错误: {e}")
        raise

@app.route('/api/getinfo', methods=['GET'])
@api_key_required
def get_info():
    hostname = request.args.get('hostname')
    if not hostname:
        return jsonify({'code': 400, 'msg': '缺少hostname参数'}), 400

    container = get_container_or_404(hostname)
    if not container:
        return jsonify({'code': 404, 'msg': '容器未找到'}), 404

    try:
        state = container.state()
        container_config = container.config

        total_ram_mb = 0
        if 'limits.memory' in container_config:
            memory_limit = container_config.get('limits.memory', '0MB')
            if memory_limit.upper().endswith('MB'):
                total_ram_mb = int(memory_limit[:-2])
            elif memory_limit.upper().endswith('GB'):
                total_ram_mb = int(memory_limit[:-2]) * 1024
        
        used_ram_mb = 0
        if state.memory and 'usage' in state.memory:
            used_ram_mb = int(state.memory['usage'] / (1024 * 1024))

        total_disk_mb = 0
        used_disk_mb = 0
        
        root_device = container.devices.get('root', {})
        if root_device and 'size' in root_device:
            disk_size_str = root_device['size']
            if disk_size_str.upper().endswith('MB'):
                total_disk_mb = int(disk_size_str[:-2])
            elif disk_size_str.upper().endswith('GB'):
                total_disk_mb = int(disk_size_str[:-2]) * 1024
        elif 'volatile.rootfs.size' in container_config: # Fallback for some configurations
             total_disk_mb = int(int(container_config['volatile.rootfs.size']) / (1024*1024))


        if state.disk and 'root' in state.disk and 'usage' in state.disk['root']:
             used_disk_mb = int(state.disk['root']['usage'] / (1024 * 1024))


        status_map = {
            'Running': 'running',
            'Stopped': 'stop',
            'Frozen': 'frozen',
            'Error': 'error'
        }
        
        lxc_status = status_map.get(state.status, 'unknown')

        data = {
            'Hostname': hostname,
            'Status': lxc_status,
            'TotalRam': total_ram_mb,
            'UsedRam': used_ram_mb,
            'TotalDisk': total_disk_mb, 
            'UsedDisk': used_disk_mb,
            'IP': state.network[config['NET_INTERFACE']]['addresses'][0]['address'] if config['NET_INTERFACE'] in state.network and state.network[config['NET_INTERFACE']]['addresses'] else 'N/A',
            'Bandwidth': 0, 
            'UseBandwidth': 0, 
        }
        return jsonify({'code': 200, 'msg': '获取成功', 'data': data})
    except LXDAPIException as e:
        return jsonify({'code': 500, 'msg': f'LXD API错误: {e}'}), 500
    except Exception as e:
        app.logger.error(f"处理 /api/getinfo 时发生错误: {e}")
        return jsonify({'code': 500, 'msg': f'内部服务器错误: {e}'}), 500


@app.route('/api/create', methods=['POST'])
@api_key_required
def create_account():
    try:
        payload = request.json
        if not payload:
            return jsonify({'code': 400, 'msg': '请求体不能为空'}), 400

        hostname = payload.get('hostname')
        password = payload.get('password')
        cpu_cores = payload.get('cpu', '1')
        disk_space_mb = payload.get('disk', '1024')
        memory_mb = payload.get('ram', '128')
        os_image_alias = payload.get('system') or config['DEFAULT_IMAGE']
        
        net_in_mbps = payload.get('up', '1') # 需要转换为 bytes/sec for LXD
        net_out_mbps = payload.get('down', '1') # 需要转换为 bytes/sec for LXD

        if not all([hostname, password, os_image_alias]):
            return jsonify({'code': 400, 'msg': '缺少必要参数 (hostname, password, system)'}), 400
        
        if lxd_client.containers.exists(hostname):
            return jsonify({'code': 409, 'msg': '容器已存在'}), 409

        container_config = {
            'name': hostname,
            'source': {'type': 'image', 'alias': os_image_alias},
            'config': {
                'limits.cpu': str(cpu_cores),
                'limits.memory': f'{memory_mb}MB',
                'security.nesting': 'true', # 视需求而定
                'user.user-data': f"#cloud-config\npassword: {password}\nchpasswd: {{ expire: False }}\nssh_pwauth: True"
            },
            'devices': {
                'root': {
                    'path': '/',
                    'pool': config['STORAGE_POOL'],
                    'size': f'{disk_space_mb}MB',
                    'type': 'disk'
                },
                'eth0': { # 假设容器内网卡为eth0，连接到LXD的桥接网络
                    'name': 'eth0',
                    'network': config['NET_INTERFACE'],
                    'type': 'nic',
                    # 'limits.ingress': f'{int(net_in_mbps) * 125000}', # Mbps to Bytes/s
                    # 'limits.egress': f'{int(net_out_mbps) * 125000}'  # Mbps to Bytes/s
                }
            }
        }
        
        app.logger.info(f"尝试创建容器 {hostname} 使用配置: {container_config}")
        container = lxd_client.containers.create(container_config, wait=True)
        container.start(wait=True)
        
        return jsonify({'code': 200, 'msg': '容器创建成功'})
    except LXDAPIException as e:
        app.logger.error(f"LXD API错误 (创建容器): {e}")
        return jsonify({'code': 500, 'msg': f'LXD API错误: {e.response.json().get("error", str(e)) if e.response else str(e)}'}), 500
    except Exception as e:
        app.logger.error(f"创建容器时发生内部错误: {e}", exc_info=True)
        return jsonify({'code': 500, 'msg': f'内部服务器错误: {e}'}), 500

@app.route('/api/delete', methods=['GET']) # PHP插件中使用GET，但DELETE更合适
@api_key_required
def terminate_account():
    hostname = request.args.get('hostname')
    if not hostname:
        return jsonify({'code': 400, 'msg': '缺少hostname参数'}), 400

    container = get_container_or_404(hostname)
    if not container:
        return jsonify({'code': 404, 'msg': '容器未找到'}), 404
    
    try:
        if container.status == 'Running':
            container.stop(wait=True)
        container.delete(wait=True)
        return jsonify({'code': 200, 'msg': '容器删除成功'})
    except LXDAPIException as e:
        return jsonify({'code': 500, 'msg': f'LXD API错误: {e}'}), 500

def _change_container_state(hostname, action):
    container = get_container_or_404(hostname)
    if not container:
        return jsonify({'code': 404, 'msg': '容器未找到'}), 404
    try:
        if action == 'boot':
            if container.status == 'Running':
                return jsonify({'code': 200, 'msg': '容器已在运行'})
            container.start(wait=True)
            msg = '容器启动成功'
        elif action == 'stop':
            if container.status == 'Stopped':
                return jsonify({'code': 200, 'msg': '容器已停止'})
            container.stop(wait=True)
            msg = '容器停止成功'
        elif action == 'reboot':
            container.restart(wait=True)
            msg = '容器重启成功'
        else:
            return jsonify({'code': 400, 'msg': '无效的操作'}), 400
        return jsonify({'code': 200, 'msg': msg})
    except LXDAPIException as e:
        return jsonify({'code': 500, 'msg': f'LXD API错误: {e}'}), 500

@app.route('/api/boot', methods=['GET'])
@api_key_required
def boot_container():
    hostname = request.args.get('hostname')
    if not hostname: return jsonify({'code': 400, 'msg': '缺少hostname参数'}), 400
    return _change_container_state(hostname, 'boot')

@app.route('/api/stop', methods=['GET'])
@api_key_required
def stop_container():
    hostname = request.args.get('hostname')
    if not hostname: return jsonify({'code': 400, 'msg': '缺少hostname参数'}), 400
    return _change_container_state(hostname, 'stop')

@app.route('/api/reboot', methods=['GET'])
@api_key_required
def reboot_container():
    hostname = request.args.get('hostname')
    if not hostname: return jsonify({'code': 400, 'msg': '缺少hostname参数'}), 400
    return _change_container_state(hostname, 'reboot')

@app.route('/api/password', methods=['POST'])
@api_key_required
def change_password():
    payload = request.json
    hostname = payload.get('hostname')
    new_password = payload.get('password')

    if not all([hostname, new_password]):
        return jsonify({'code': 400, 'msg': '缺少hostname或password参数'}), 400

    container = get_container_or_404(hostname)
    if not container:
        return jsonify({'code': 404, 'msg': '容器未找到'}), 404
    
    if container.status != 'Running':
        return jsonify({'code': 400, 'msg': '容器未在运行状态，无法修改密码'}), 400

    try:
        # 注意：下面的命令假设容器内有 'root' 用户，并且可以使用 chpasswd
        # 对于不同镜像，用户名和修改密码的方式可能不同
        # 更可靠的方式是使用 cloud-init 在下次启动时更新密码，但这会涉及重启
        exit_code, stdout, stderr = container.execute(['chpasswd'], stdin=f"root:{new_password}\n")
        if exit_code == 0:
            return jsonify({'code': 200, 'msg': '密码修改成功'})
        else:
            app.logger.error(f"修改密码失败 for {hostname}: {stderr.decode() if stderr else '未知错误'}")
            return jsonify({'code': 500, 'msg': f'密码修改失败: {stderr.decode() if stderr else "未知错误"}'}), 500
    except LXDAPIException as e:
        return jsonify({'code': 500, 'msg': f'LXD API错误: {e}'}), 500
    except Exception as e:
        app.logger.error(f"修改密码时发生内部错误: {e}")
        return jsonify({'code': 500, 'msg': f'内部服务器错误: {e}'}), 500


@app.route('/api/reinstall', methods=['POST'])
@api_key_required
def reinstall_container():
    payload = request.json
    hostname = payload.get('hostname')
    new_os_alias = payload.get('system')

    if not all([hostname, new_os_alias]):
        return jsonify({'code': 400, 'msg': '缺少hostname或system参数'}), 400

    container = get_container_or_404(hostname)
    if not container:
        return jsonify({'code': 404, 'msg': '容器未找到'}), 404
    
    try:
        current_config = container.config
        current_devices = container.devices
        
        if container.status == 'Running':
            container.stop(wait=True)
        container.delete(wait=True)

        reinstall_config = {
            'name': hostname,
            'source': {'type': 'image', 'alias': new_os_alias},
            'config': {k: v for k, v in current_config.items() if k.startswith('limits.') or k.startswith('security.')}, # 保留部分配置
            'devices': current_devices 
        }
        # 确保 user.user-data 中的密码信息也被更新或移除，或者通过PHP插件传递新密码
        if 'user.user-data' in reinstall_config['config']:
            # 假设密码参数也包含在最初的创建请求中，或需要新的默认密码
            # 这里简单地移除了旧的，理想情况下应该更新
             del reinstall_config['config']['user.user-data'] 

        new_container = lxd_client.containers.create(reinstall_config, wait=True)
        new_container.start(wait=True)
        
        return jsonify({'code': 200, 'msg': '系统重装成功'})
    except LXDAPIException as e:
        app.logger.error(f"LXD API错误 (重装): {e}")
        return jsonify({'code': 500, 'msg': f'LXD API错误: {e.response.json().get("error", str(e)) if e.response else str(e)}'}), 500
    except Exception as e:
        app.logger.error(f"重装系统时发生内部错误: {e}", exc_info=True)
        return jsonify({'code': 500, 'msg': f'内部服务器错误: {e}'}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=config['HTTP_PORT'], debug=False)
