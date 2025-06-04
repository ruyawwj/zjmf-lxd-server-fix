from pylxd import Client as LXDClient
from pylxd.exceptions import LXDAPIException, NotFound
from config_handler import app_config
import apache_manager

class LXCManager:
    def __init__(self):
        try:
            self.client = LXDClient()
        except LXDAPIException as e:
            raise RuntimeError(f"无法连接到LXD守护进程: {e}")

    def _get_container_or_error(self, hostname):
        try:
            return self.client.containers.get(hostname)
        except NotFound:
            return None
        except LXDAPIException as e:
            raise ValueError(f"获取容器时LXD API错误: {e}")

    def _get_container_ip(self, container, bridge_name=None):
        bridge = bridge_name or app_config.network_bridge
        try:
            state = container.state()
            if state.network and bridge in state.network:
                for addr_info in state.network[bridge]['addresses']:
                    if addr_info['family'] == 'inet' and addr_info['scope'] == 'global':
                        return addr_info['address']
        except LXDAPIException:
            pass
        return None

    def _get_user_metadata(self, container, key, default=None):
        return container.config.get(f"user.{key}", default)

    def _set_user_metadata(self, container, key, value):
        container.config[f"user.{key}"] = str(value)
        container.save(wait=True)

    def get_container_info(self, hostname):
        container = self._get_container_or_error(hostname)
        if not container:
            return {'code': 404, 'msg': '容器未找到'}
        
        try:
            state = container.state()
            config = container.config

            total_ram_mb = 0
            mem_limit = config.get('limits.memory', '0MB')
            if mem_limit.upper().endswith('MB'): total_ram_mb = int(mem_limit[:-2])
            elif mem_limit.upper().endswith('GB'): total_ram_mb = int(mem_limit[:-2]) * 1024
            
            used_ram_mb = int(state.memory['usage'] / (1024*1024)) if state.memory and 'usage' in state.memory else 0

            total_disk_mb = 0
            root_device = container.devices.get('root', {})
            if 'size' in root_device:
                disk_size = root_device['size']
                if disk_size.upper().endswith('MB'): total_disk_mb = int(disk_size[:-2])
                elif disk_size.upper().endswith('GB'): total_disk_mb = int(disk_size[:-2]) * 1024
            
            used_disk_mb = int(state.disk['root']['usage'] / (1024*1024)) if state.disk and 'root' in state.disk and 'usage' in state.disk['root'] else 0
            
            status_map = {'Running': 'running', 'Stopped': 'stop', 'Frozen': 'frozen'}
            lxc_status = status_map.get(state.status, 'unknown')
            
            flow_limit_gb = int(self._get_user_metadata(container, 'flow_limit_gb', 0))
            
            bytes_total = 0
            if state.network:
                for nic_name, nic_data in state.network.items():
                    if 'counters' in nic_data:
                        bytes_total += nic_data['counters'].get('bytes_received', 0)
                        bytes_total += nic_data['counters'].get('bytes_sent', 0)
            used_flow_gb = round(bytes_total / (1024*1024*1024), 2)


            data = {
                'Hostname': hostname, 'Status': lxc_status,
                'TotalRam': total_ram_mb, 'UsedRam': used_ram_mb,
                'TotalDisk': total_disk_mb, 'UsedDisk': used_disk_mb,
                'IP': self._get_container_ip(container) or 'N/A',
                'Bandwidth': flow_limit_gb,
                'UseBandwidth': used_flow_gb,
            }
            return {'code': 200, 'msg': '获取成功', 'data': data}
        except LXDAPIException as e:
            return {'code': 500, 'msg': f'LXD API错误 (getinfo): {e}'}
        except Exception as e:
            return {'code': 500, 'msg': f'获取信息时发生内部错误: {str(e)}'}

    def create_container(self, params):
        hostname = params.get('hostname')
        if self.client.containers.exists(hostname):
            return {'code': 409, 'msg': '容器已存在'}

        image_alias = params.get('system') or app_config.default_image_alias
        container_config = {
            'name': hostname,
            'source': {'type': 'image', 'alias': image_alias},
            'config': {
                'limits.cpu': str(params.get('cpu', '1')),
                'limits.memory': f"{params.get('ram', '128')}MB",
                'security.nesting': 'true',
                'user.user-data': f"#cloud-config\nuser: {app_config.default_container_user}\npassword: {params.get('password')}\nchpasswd: {{ expire: False }}\nssh_pwauth: True"
            },
            'devices': {
                'root': {
                    'path': '/', 'pool': app_config.storage_pool,
                    'size': f"{params.get('disk', '1024')}MB", 'type': 'disk'
                },
                'eth0': {
                    'name': 'eth0', 'network': app_config.network_bridge, 'type': 'nic'
                }
            }
        }
        if params.get('up') and params.get('down'):
            container_config['devices']['eth0']['limits.ingress'] = f"{int(params.get('up'))*125000}"
            container_config['devices']['eth0']['limits.egress'] = f"{int(params.get('down'))*125000}"


        try:
            container = self.client.containers.create(container_config, wait=True)
            self._set_user_metadata(container, 'nat_acl_limit', params.get('ports', 0))
            self._set_user_metadata(container, 'domain_acl_limit', params.get('domains', 0))
            self._set_user_metadata(container, 'flow_limit_gb', params.get('bandwidth', 0))
            container.start(wait=True)
            return {'code': 200, 'msg': '容器创建成功'}
        except LXDAPIException as e:
            return {'code': 500, 'msg': f'LXD API错误 (create): {e}'}

    def delete_container(self, hostname):
        container = self._get_container_or_error(hostname)
        if not container: return {'code': 404, 'msg': '容器未找到'}
        try:
            if container.status == 'Running': container.stop(wait=True)
            container.delete(wait=True)
            bindings = self.list_domain_bindings(hostname, internal_call=True)
            if bindings.get('code') == 200:
                for binding in bindings.get('data', []):
                    self.delete_domain_binding(hostname, binding['Domain'])
            return {'code': 200, 'msg': '容器删除成功'}
        except LXDAPIException as e:
            return {'code': 500, 'msg': f'LXD API错误 (delete): {e}'}

    def _power_action(self, hostname, action):
        container = self._get_container_or_error(hostname)
        if not container: return {'code': 404, 'msg': '容器未找到'}
        try:
            if action == 'start':
                if container.status == 'Running': return {'code': 200, 'msg': '容器已在运行中'}
                container.start(wait=True)
            elif action == 'stop':
                if container.status == 'Stopped': return {'code': 200, 'msg': '容器已停止'}
                container.stop(wait=True)
            elif action == 'restart':
                container.restart(wait=True)
            return {'code': 200, 'msg': f'容器{action}操作成功'}
        except LXDAPIException as e:
            return {'code': 500, 'msg': f'LXD API错误 ({action}): {e}'}

    def start_container(self, hostname): return self._power_action(hostname, 'start')
    def stop_container(self, hostname): return self._power_action(hostname, 'stop')
    def restart_container(self, hostname): return self._power_action(hostname, 'restart')

    def change_password(self, hostname, new_password):
        container = self._get_container_or_error(hostname)
        if not container: return {'code': 404, 'msg': '容器未找到'}
        if container.status != 'Running': return {'code': 400, 'msg': '容器未运行'}
        try:
            user = app_config.default_container_user
            exit_code, _, stderr = container.execute(['chpasswd'], stdin=f"{user}:{new_password}\n")
            if exit_code == 0: return {'code': 200, 'msg': '密码修改成功'}
            return {'code': 500, 'msg': f'密码修改失败: {stderr.decode() if stderr else "未知错误"}'}
        except LXDAPIException as e:
            return {'code': 500, 'msg': f'LXD API错误 (password): {e}'}

    def reinstall_container(self, hostname, new_os_alias):
        container = self._get_container_or_error(hostname)
        if not container: return {'code': 404, 'msg': '容器未找到'}
        
        original_config_keys = ['limits.cpu', 'limits.memory', 'user.nat_acl_limit', 'user.domain_acl_limit', 'user.flow_limit_gb']
        original_devices_to_keep_config = ['eth0']

        preserved_config = {k: v for k, v in container.config.items() if k in original_config_keys}
        preserved_devices = {dev_name: dev_data for dev_name, dev_data in container.devices.items() if dev_name in original_devices_to_keep_config}
        
        root_device_config = container.devices.get('root', {})
        new_root_size = root_device_config.get('size', f"{self._get_user_metadata(container, 'disk_size_mb', '1024')}MB")


        try:
            if container.status == 'Running': container.stop(wait=True)
            container.delete(wait=True)
            
            reinstall_lxd_config = {
                'name': hostname,
                'source': {'type': 'image', 'alias': new_os_alias or app_config.default_image_alias},
                'config': preserved_config,
                'devices': preserved_devices
            }
            reinstall_lxd_config['devices']['root'] = {'path': '/', 'pool': app_config.storage_pool, 'size': new_root_size, 'type': 'disk'}
             
            new_container = self.client.containers.create(reinstall_lxd_config, wait=True)
            new_container.start(wait=True)
            return {'code': 200, 'msg': '系统重装成功'}
        except LXDAPIException as e:
            return {'code': 500, 'msg': f'LXD API错误 (reinstall): {e}'}

    def list_nat_rules(self, hostname):
        container = self._get_container_or_error(hostname)
        if not container: return {'code': 404, 'msg': '容器未找到'}
        rules = []
        for name, device in container.devices.items():
            if device.get('type') == 'proxy' and device.get('listen'):
                listen_parts = device['listen'].split(':')
                connect_parts = device['connect'].split(':')
                if len(listen_parts) >= 3 and len(connect_parts) >=3:
                    rules.append({
                        'Dtype': listen_parts[0].upper(),
                        'Dport': listen_parts[-1],
                        'Sport': connect_parts[-1],
                        'ID': name
                    })
        return {'code': 200, 'msg': '获取成功', 'data': rules}

    def add_nat_rule(self, hostname, dtype, dport, sport):
        container = self._get_container_or_error(hostname)
        if not container: return {'code': 404, 'msg': '容器未找到'}

        limit = int(self._get_user_metadata(container, 'nat_acl_limit', 0))
        current_rules_resp = self.list_nat_rules(hostname)
        if current_rules_resp['code'] == 200 and limit > 0 and len(current_rules_resp['data']) >= limit:
            return {'code': 403, 'msg': f'已达到NAT规则数量上限 ({limit}条)'}

        device_name = f"nat-{dtype.lower()}-{dport}"
        if device_name in container.devices:
            return {'code': 409, 'msg': '此外部端口和协议的NAT规则已存在'}
        
        container_ip = self._get_container_ip(container)
        if not container_ip:
            return {'code': 500, 'msg': '无法获取容器内部IP地址'}

        proxy_device_config = {
            'type': 'proxy',
            'listen': f"{dtype.lower()}:0.0.0.0:{dport}",
            'connect': f"{dtype.lower()}:{container_ip}:{sport}",
            'nat': 'true'
        }
        try:
            container.devices[device_name] = proxy_device_config
            container.save(wait=True)
            return {'code': 200, 'msg': 'NAT规则添加成功'}
        except LXDAPIException as e:
            return {'code': 500, 'msg': f'LXD API错误 (add nat): {e}'}

    def delete_nat_rule(self, hostname, dtype, dport, sport):
        container = self._get_container_or_error(hostname)
        if not container: return {'code': 404, 'msg': '容器未找到'}
        device_name = f"nat-{dtype.lower()}-{dport}"
        if device_name not in container.devices:
            return {'code': 404, 'msg': 'NAT规则未找到'}
        try:
            del container.devices[device_name]
            container.save(wait=True)
            return {'code': 200, 'msg': 'NAT规则删除成功'}
        except LXDAPIException as e:
            return {'code': 500, 'msg': f'LXD API错误 (delete nat): {e}'}

    def list_domain_bindings(self, hostname, internal_call=False):
        if not internal_call:
            container = self._get_container_or_error(hostname)
            if not container: return {'code': 404, 'msg': '容器未找到'}
        
        all_bindings = apache_manager.list_apache_bindings()
        
        if internal_call:
             return {'code': 200, 'msg': '获取成功', 'data': all_bindings }

        return {'code': 200, 'msg': '获取成功 (当前返回所有全局绑定)', 'data': all_bindings}


    def add_domain_binding(self, hostname, domain):
        container = self._get_container_or_error(hostname)
        if not container: return {'code': 404, 'msg': '容器未找到'}

        limit = int(self._get_user_metadata(container, 'domain_acl_limit', 0))
        current_bindings_resp = self.list_domain_bindings(hostname)

        container_ip = self._get_container_ip(container)
        if not container_ip:
            return {'code': 500, 'msg': '无法获取容器内部IP地址'}

        success, msg = apache_manager.create_apache_vhost(domain, container_ip)
        if success:
            return {'code': 200, 'msg': msg}
        return {'code': 500, 'msg': msg}

    def delete_domain_binding(self, hostname, domain):

        success, msg = apache_manager.delete_apache_vhost(domain)
        if success:
            return {'code': 200, 'msg': msg}
        return {'code': 500, 'msg': msg}
