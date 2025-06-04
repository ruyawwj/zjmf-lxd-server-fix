from pylxd import Client as LXDClient
from pylxd.exceptions import LXDAPIException, NotFound
from config_handler import app_config
import apache_manager
import logging
import json
import subprocess
import os

logger = logging.getLogger(__name__)

IPTABLES_RULES_METADATA_FILE = 'iptables_rules.json'

def _load_iptables_rules_metadata():
    try:
        if os.path.exists(IPTABLES_RULES_METADATA_FILE):
            with open(IPTABLES_RULES_METADATA_FILE, 'r') as f:
                return json.load(f)
        return []
    except Exception as e:
        logger.error(f"加载iptables规则元数据失败: {e}")
        return []

def _save_iptables_rules_metadata(rules):
    try:
        with open(IPTABLES_RULES_METADATA_FILE, 'w') as f:
            json.dump(rules, f, indent=4)
    except Exception as e:
        logger.error(f"保存iptables规则元数据失败: {e}")

class LXCManager:
    def __init__(self):
        try:
            self.client = LXDClient()
        except LXDAPIException as e:
            logger.critical(f"无法连接到LXD守护进程: {e}")
            raise RuntimeError(f"无法连接到LXD守护进程: {e}")

    def _get_container_or_error(self, hostname):
        try:
            return self.client.containers.get(hostname)
        except NotFound:
            return None
        except LXDAPIException as e:
            logger.error(f"获取容器 {hostname} 时发生LXD API错误: {e}")
            raise ValueError(f"获取容器时LXD API错误: {e}")

    def _get_container_ip(self, container):
        target_bridge = app_config.network_bridge
        nic_name_on_target_bridge = None
        container_name = container.name

        logger.debug(f"开始为容器 {container_name} 获取IP地址，目标网桥: {target_bridge}")

        for device_name, device_config in container.devices.items():
            if device_config.get('type') == 'nic' and device_config.get('network') == target_bridge:
                nic_name_on_target_bridge = device_name
                logger.debug(f"容器 {container_name} 上找到连接到网桥 {target_bridge} 的接口设备: {nic_name_on_target_bridge}")
                break

        if not nic_name_on_target_bridge:
            logger.warning(f"容器 {container_name} 没有找到连接到网桥 {target_bridge} 的网络接口设备。设备列表: {container.devices}")
            return None

        try:
            state = container.state()
            if state.network and nic_name_on_target_bridge in state.network:
                interface_state = state.network[nic_name_on_target_bridge]
                logger.debug(f"容器 {container_name} 接口 {nic_name_on_target_bridge} 的状态: {interface_state}")
                for addr_info in interface_state.get('addresses', []):
                    if addr_info.get('family') == 'inet' and addr_info.get('scope') == 'global':
                        ip_address = addr_info['address']
                        logger.info(f"为容器 {container_name} 在接口 {nic_name_on_target_bridge} 上找到IP: {ip_address}")
                        return ip_address
                logger.warning(f"容器 {container_name} 在接口 {nic_name_on_target_bridge} 上没有找到inet global IP地址。地址列表: {interface_state.get('addresses')}")
            else:
                logger.warning(f"容器 {container_name} 的网络状态中没有接口 {nic_name_on_target_bridge} 的信息。当前网络状态: {state.network}")
        except LXDAPIException as e:
            logger.error(f"获取容器 {container_name} 网络状态时发生LXD API错误: {e}")

        logger.warning(f"未能为容器 {container_name} 获取IP地址")
        return None

    def _get_user_metadata(self, container, key, default=None):
        return container.config.get(f"user.{key}", default)

    def _set_user_metadata(self, container, key, value):
        container.config[f"user.{key}"] = str(value)
        container.save(wait=True)

    def _run_shell_command_for_iptables(self, command_args):
        full_command = ['sudo', 'iptables'] + command_args
        try:
            logger.debug(f"执行iptables命令: {' '.join(full_command)}")
            process = subprocess.Popen(full_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, stderr = process.communicate(timeout=15)
            if process.returncode != 0:
                error_message = stderr.decode('utf-8', errors='ignore').strip()
                logger.error(f"iptables命令执行失败 ({process.returncode}): {error_message}. 命令: {' '.join(full_command)}")
                return False, f"iptables命令执行失败: {error_message}"
            logger.info(f"iptables命令成功执行: {' '.join(full_command)}")
            return True, stdout.decode('utf-8', errors='ignore').strip()
        except subprocess.TimeoutExpired:
            logger.error(f"iptables命令超时: {' '.join(full_command)}")
            return False, "iptables命令执行超时"
        except FileNotFoundError:
            logger.error(f"iptables命令未找到，请检查路径: {full_command[0]}")
            return False, "iptables命令未找到"
        except Exception as e:
            logger.error(f"执行iptables命令时发生异常: {str(e)}. 命令: {' '.join(full_command)}")
            return False, f"执行iptables命令时发生异常: {str(e)}"

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
            logger.error(f"LXD API错误 (getinfo) for {hostname}: {e}")
            return {'code': 500, 'msg': f'LXD API错误 (getinfo): {e}'}
        except Exception as e:
            logger.error(f"获取信息时发生内部错误 for {hostname}: {str(e)}", exc_info=True)
            return {'code': 500, 'msg': f'获取信息时发生内部错误: {str(e)}'}

    def create_container(self, params):
        hostname = params.get('hostname')
        if self.client.containers.exists(hostname):
            return {'code': 409, 'msg': '容器已存在'}
        image_alias = params.get('system') or app_config.default_image_alias
        container_config_obj = {
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
            container_config_obj['devices']['eth0']['limits.ingress'] = f"{int(params.get('up'))*125000}"
            container_config_obj['devices']['eth0']['limits.egress'] = f"{int(params.get('down'))*125000}"
        try:
            logger.info(f"开始创建容器 {hostname} 使用配置: {container_config_obj}")
            container = self.client.containers.create(container_config_obj, wait=True)
            self._set_user_metadata(container, 'nat_acl_limit', params.get('ports', 0))
            self._set_user_metadata(container, 'domain_acl_limit', params.get('domains', 0))
            self._set_user_metadata(container, 'flow_limit_gb', params.get('bandwidth', 0))
            self._set_user_metadata(container, 'disk_size_mb', params.get('disk', '1024'))
            logger.info(f"容器 {hostname} 配置完成，开始启动...")
            container.start(wait=True)
            logger.info(f"容器 {hostname} 启动成功")
            return {'code': 200, 'msg': '容器创建成功'}
        except LXDAPIException as e:
            logger.error(f"LXD API错误 (create container {hostname}): {e}")
            return {'code': 500, 'msg': f'LXD API错误 (create): {e}'}
        except Exception as e:
            logger.error(f"创建容器 {hostname} 时发生内部错误: {str(e)}", exc_info=True)
            return {'code': 500, 'msg': f'创建容器时发生内部错误: {str(e)}'}

    def delete_container(self, hostname):
        container = self._get_container_or_error(hostname)
        if not container: return {'code': 404, 'msg': '容器未找到'}
        try:
            logger.info(f"开始删除容器 {hostname}")

            rules_metadata = _load_iptables_rules_metadata()
            rules_to_keep = []
            rules_for_this_container_found = False
            for rule_meta in rules_metadata:
                if rule_meta.get('hostname') == hostname:
                    logger.info(f"准备删除容器 {hostname} 的iptables规则: {rule_meta}")
                    self.delete_nat_rule_via_iptables(
                        hostname,
                        rule_meta['dtype'],
                        rule_meta['dport'],
                        rule_meta['sport'],
                        container_ip_at_creation_time=rule_meta['container_ip']
                    )
                    rules_for_this_container_found = True
                else:
                    rules_to_keep.append(rule_meta)
            if rules_for_this_container_found:
                _save_iptables_rules_metadata(rules_to_keep)

            if container.status == 'Running':
                logger.info(f"容器 {hostname} 正在运行，先停止...")
                container.stop(wait=True)

            bindings_before_delete = self.list_domain_bindings(hostname, internal_call=True)

            container.delete(wait=True)
            logger.info(f"容器 {hostname} 删除成功")

            if bindings_before_delete.get('code') == 200:
                for binding in bindings_before_delete.get('data', []):
                    if 'Domain' in binding and binding['Domain']:
                        logger.info(f"尝试删除容器 {hostname} 关联的域名绑定: {binding['Domain']}")
                        apache_manager.delete_apache_vhost(binding['Domain'])
            return {'code': 200, 'msg': '容器删除成功'}
        except LXDAPIException as e:
            logger.error(f"LXD API错误 (delete container {hostname}): {e}")
            return {'code': 500, 'msg': f'LXD API错误 (delete): {e}'}
        except Exception as e:
            logger.error(f"删除容器 {hostname} 时发生内部错误: {str(e)}", exc_info=True)
            return {'code': 500, 'msg': f'删除容器时发生内部错误: {str(e)}'}

    def _power_action(self, hostname, action):
        container = self._get_container_or_error(hostname)
        if not container: return {'code': 404, 'msg': '容器未找到'}
        try:
            logger.info(f"对容器 {hostname} 执行电源操作: {action}")
            if action == 'start':
                if container.status == 'Running': return {'code': 200, 'msg': '容器已在运行中'}
                container.start(wait=True)
            elif action == 'stop':
                if container.status == 'Stopped': return {'code': 200, 'msg': '容器已停止'}
                container.stop(wait=True)
            elif action == 'restart':
                container.restart(wait=True)
            logger.info(f"容器 {hostname} {action} 操作成功")
            return {'code': 200, 'msg': f'容器{action}操作成功'}
        except LXDAPIException as e:
            logger.error(f"LXD API错误 (power action {action} for {hostname}): {e}")
            return {'code': 500, 'msg': f'LXD API错误 ({action}): {e}'}
        except Exception as e:
            logger.error(f"电源操作 {action} for {hostname} 时发生内部错误: {str(e)}", exc_info=True)
            return {'code': 500, 'msg': f'电源操作时发生内部错误: {str(e)}'}

    def start_container(self, hostname): return self._power_action(hostname, 'start')
    def stop_container(self, hostname): return self._power_action(hostname, 'stop')
    def restart_container(self, hostname): return self._power_action(hostname, 'restart')

    def change_password(self, hostname, new_password):
        container = self._get_container_or_error(hostname)
        if not container: return {'code': 404, 'msg': '容器未找到'}
        if container.status != 'Running': return {'code': 400, 'msg': '容器未运行'}
        try:
            user = app_config.default_container_user
            logger.info(f"开始为容器 {hostname} 的用户 {user} 修改密码")
            exit_code, _, stderr = container.execute(['chpasswd'], stdin=f"{user}:{new_password}\n")
            if exit_code == 0:
                logger.info(f"容器 {hostname} 密码修改成功")
                return {'code': 200, 'msg': '密码修改成功'}
            err_msg = stderr.decode() if stderr else "未知错误"
            logger.error(f"容器 {hostname} 密码修改失败: {err_msg}")
            return {'code': 500, 'msg': f'密码修改失败: {err_msg}'}
        except LXDAPIException as e:
            logger.error(f"LXD API错误 (change password for {hostname}): {e}")
            return {'code': 500, 'msg': f'LXD API错误 (password): {e}'}
        except Exception as e:
            logger.error(f"修改密码 for {hostname} 时发生内部错误: {str(e)}", exc_info=True)
            return {'code': 500, 'msg': f'修改密码时发生内部错误: {str(e)}'}

    def reinstall_container(self, hostname, new_os_alias):
        container = self._get_container_or_error(hostname)
        if not container: return {'code': 404, 'msg': '容器未找到'}
        logger.info(f"开始重装容器 {hostname} 为系统 {new_os_alias}")
        original_config_keys = ['limits.cpu', 'limits.memory', 'user.nat_acl_limit', 'user.domain_acl_limit', 'user.flow_limit_gb', 'user.disk_size_mb']
        if 'user.user-data' in container.config:
             original_config_keys.append('user.user-data')
        original_devices_to_keep_config = ['eth0']
        preserved_config = {k: v for k, v in container.config.items() if k in original_config_keys}
        preserved_devices = {dev_name: dev_data for dev_name, dev_data in container.devices.items() if dev_name in original_devices_to_keep_config}
        new_root_size = self._get_user_metadata(container, 'disk_size_mb', '1024') + "MB"
        try:
            if container.status == 'Running':
                logger.info(f"容器 {hostname}正在运行，重装前先停止...")
                container.stop(wait=True)
            logger.info(f"准备删除旧容器 {hostname}...")
            container.delete(wait=True)
            logger.info(f"旧容器 {hostname} 已删除，开始创建新容器...")
            reinstall_lxd_config = {
                'name': hostname,
                'source': {'type': 'image', 'alias': new_os_alias or app_config.default_image_alias},
                'config': preserved_config,
                'devices': preserved_devices
            }
            reinstall_lxd_config['devices']['root'] = {'path': '/', 'pool': app_config.storage_pool, 'size': new_root_size, 'type': 'disk'}
            new_container = self.client.containers.create(reinstall_lxd_config, wait=True)
            logger.info(f"新容器 {hostname} 配置完成，开始启动...")
            new_container.start(wait=True)
            logger.info(f"容器 {hostname} 重装并启动成功")
            return {'code': 200, 'msg': '系统重装成功'}
        except LXDAPIException as e:
            logger.error(f"LXD API错误 (reinstall {hostname}): {e}")
            return {'code': 500, 'msg': f'LXD API错误 (reinstall): {e}'}
        except Exception as e:
            logger.error(f"重装容器 {hostname} 时发生内部错误: {str(e)}", exc_info=True)
            return {'code': 500, 'msg': f'重装容器时发生内部错误: {str(e)}'}

    def list_nat_rules(self, hostname):
        logger.debug(f"列出容器 {hostname} 的iptables NAT规则 (基于元数据)")
        rules_metadata = _load_iptables_rules_metadata()
        container_rules = []
        for rule_meta in rules_metadata:
            if rule_meta.get('hostname') == hostname:
                container_rules.append({
                    'Dtype': rule_meta.get('dtype','').upper(),
                    'Dport': rule_meta.get('dport'),
                    'Sport': rule_meta.get('sport'),
                    'ID': rule_meta.get('rule_id', f"iptables-{rule_meta.get('dtype')}-{rule_meta.get('dport')}")
                })
        logger.info(f"容器 {hostname} iptables NAT规则列表: {container_rules}")
        return {'code': 200, 'msg': '获取成功', 'data': container_rules}

    def add_nat_rule_via_iptables(self, hostname, dtype, dport, sport):
        container = self._get_container_or_error(hostname)
        if not container: return {'code': 404, 'msg': '容器未找到'}

        logger.info(f"为容器 {hostname} 通过iptables添加NAT规则: {dtype} {dport} -> {sport}")

        limit = int(self._get_user_metadata(container, 'nat_acl_limit', 0))
        rules_metadata = _load_iptables_rules_metadata()
        current_host_rules_count = sum(1 for r in rules_metadata if r.get('hostname') == hostname)

        if limit > 0 and current_host_rules_count >= limit:
            logger.warning(f"容器 {hostname} 已达到iptables NAT规则数量上限 ({limit}条)")
            return {'code': 403, 'msg': f'已达到NAT规则数量上限 ({limit}条)'}

        for rule_meta in rules_metadata:
            if rule_meta.get('hostname') == hostname and \
               rule_meta.get('dtype', '').lower() == dtype.lower() and \
               str(rule_meta.get('dport')) == str(dport):
                logger.warning(f"容器 {hostname} 的iptables NAT规则 ({dtype} {dport}) 已存在")
                return {'code': 409, 'msg': '此外部端口和协议的NAT规则已存在'}

        container_ip = self._get_container_ip(container)
        if not container_ip:
            logger.error(f"为容器 {hostname} 添加iptables NAT规则失败: 无法获取内部IP")
            return {'code': 500, 'msg': '无法获取容器内部IP地址'}

        host_listen_ip = app_config.nat_listen_ip
        main_interface = getattr(app_config, 'main_interface', None)
        if not main_interface:
            logger.error("配置文件中缺少 main_interface (主网卡名) for iptables MASQUERADE rule")


        rule_comment = f'lxd_controller_nat_{hostname}_{dtype.lower()}_{dport}'

        dnat_args = [
            '-t', 'nat', '-A', 'PREROUTING',
            '-d', host_listen_ip,
            '-p', dtype.lower(), '--dport', str(dport),
            '-j', 'DNAT', '--to-destination', f"{container_ip}:{sport}",
            '-m', 'comment', '--comment', rule_comment
        ]
        success_dnat, msg_dnat = self._run_shell_command_for_iptables(dnat_args)
        if not success_dnat:
            return {'code': 500, 'msg': f"添加DNAT规则失败: {msg_dnat}"}

        if main_interface:
            masquerade_args = [
                '-t', 'nat', '-A', 'POSTROUTING',
                '-s', container_ip,
                '-o', main_interface,
                '-j', 'MASQUERADE',
                '-m', 'comment', '--comment', f'{rule_comment}_masq'
            ]
            success_masq, msg_masq = self._run_shell_command_for_iptables(masquerade_args)
            if not success_masq:
                dnat_del_args = ['-t', 'nat', '-D'] + dnat_args[2:]
                self._run_shell_command_for_iptables(dnat_del_args)
                return {'code': 500, 'msg': f"添加MASQUERADE规则失败: {msg_masq}"}

        new_rule_meta = {
            'hostname': hostname, 'dtype': dtype.lower(), 'dport': str(dport),
            'sport': str(sport), 'container_ip': container_ip, 'rule_id': rule_comment
        }
        rules_metadata.append(new_rule_meta)
        _save_iptables_rules_metadata(rules_metadata)

        logger.info(f"容器 {hostname} 通过iptables添加DNAT和MASQUERADE规则成功")
        return {'code': 200, 'msg': 'NAT规则(iptables)添加成功'}

    def delete_nat_rule_via_iptables(self, hostname, dtype, dport, sport, container_ip_at_creation_time=None):
        logger.info(f"为容器 {hostname} 通过iptables删除NAT规则: {dtype} {dport} -> {sport}")
        host_listen_ip = app_config.nat_listen_ip
        rules_metadata = _load_iptables_rules_metadata()
        rules_to_keep = []
        rule_found_and_deleted = False

        rule_to_delete_meta = None
        for rule_meta in rules_metadata:
            if rule_meta.get('hostname') == hostname and \
               rule_meta.get('dtype', '').lower() == dtype.lower() and \
               str(rule_meta.get('dport')) == str(dport):
                rule_to_delete_meta = rule_meta
                break

        if not rule_to_delete_meta:
            logger.warning(f"未在元数据中找到容器 {hostname} 的规则 {dtype} {dport}，可能已被删除或未正确记录")
            if not container_ip_at_creation_time:
                current_container = self._get_container_or_error(hostname)
                if current_container:
                    container_ip_at_creation_time = self._get_container_ip(current_container)
                if not container_ip_at_creation_time:
                     logger.error(f"无法确定删除规则所需的容器IP for {hostname} {dtype} {dport}")
                     return {'code': 404, 'msg': 'NAT规则元数据未找到，且无法确定容器原始IP以尝试删除'}

        if rule_to_delete_meta and not container_ip_at_creation_time:
            container_ip_at_creation_time = rule_to_delete_meta.get('container_ip')

        if not container_ip_at_creation_time:
            logger.error(f"最终无法确定删除规则所需的容器IP for {hostname} {dtype} {dport}")
            return {'code': 500, 'msg': '删除iptables规则失败: 无法确定容器原始IP'}

        rule_comment = rule_to_delete_meta.get('rule_id') if rule_to_delete_meta else f'lxd_controller_nat_{hostname}_{dtype.lower()}_{dport}'

        dnat_del_args = [
            '-t', 'nat', '-D', 'PREROUTING',
            '-d', host_listen_ip,
            '-p', dtype.lower(), '--dport', str(dport),
            '-j', 'DNAT', '--to-destination', f"{container_ip_at_creation_time}:{sport}",
            '-m', 'comment', '--comment', rule_comment
        ]
        success_dnat, msg_dnat = self._run_shell_command_for_iptables(dnat_del_args)
        if success_dnat:
            rule_found_and_deleted = True
        else:
            logger.warning(f"删除DNAT规则可能失败 (或规则不存在): {msg_dnat}")

        main_interface = getattr(app_config, 'main_interface', None)
        if main_interface:
            masquerade_del_args = [
                '-t', 'nat', '-D', 'POSTROUTING',
                '-s', container_ip_at_creation_time,
                '-o', main_interface,
                '-j', 'MASQUERADE',
                '-m', 'comment', '--comment', f'{rule_comment}_masq'
            ]
            success_masq, msg_masq = self._run_shell_command_for_iptables(masquerade_del_args)
            if not success_masq:
                 logger.warning(f"删除MASQUERADE规则可能失败 (或规则不存在): {msg_masq}")

        if rule_to_delete_meta:
            for rule_meta_item in rules_metadata:
                if rule_meta_item.get('rule_id') != rule_comment:
                    rules_to_keep.append(rule_meta_item)
            _save_iptables_rules_metadata(rules_to_keep)
            logger.info(f"从元数据中移除规则: {rule_comment}")
        elif not rule_found_and_deleted and not success_dnat :
             return {'code': 404, 'msg': 'NAT规则未找到或删除失败'}

        logger.info(f"容器 {hostname} 通过iptables删除DNAT规则尝试完成")
        return {'code': 200, 'msg': 'NAT规则(iptables)删除尝试完成'}

    def list_domain_bindings(self, hostname, internal_call=False):
        container = None
        if not internal_call:
            container = self._get_container_or_error(hostname)
            if not container: return {'code': 404, 'msg': '容器未找到'}
        logger.debug(f"列出容器 {hostname} 的域名绑定 (internal_call={internal_call})")
        if container:
            domains_json = self._get_user_metadata(container, 'bound_domains', '[]')
            try:
                bound_domains_for_container = json.loads(domains_json)
                formatted_bindings = [{'Domain': d} for d in bound_domains_for_container]
                logger.info(f"容器 {hostname} 域名绑定列表 (from metadata): {formatted_bindings}")
                return {'code': 200, 'msg': '获取成功', 'data': formatted_bindings}
            except json.JSONDecodeError:
                logger.error(f"解析容器 {hostname} 的bound_domains元数据失败: {domains_json}")
                return {'code': 200, 'msg': '获取成功 (元数据错误)', 'data': []}
        elif internal_call:
             all_apache_bindings = apache_manager.list_apache_bindings()
             logger.info(f"内部调用 list_domain_bindings for {hostname} (可能已删除), Apache列出所有: {all_apache_bindings}")
             return {'code': 200, 'msg': '获取成功 (所有Apache托管的绑定)', 'data': all_apache_bindings}
        return {'code': 200, 'msg': '获取成功 (无绑定记录或无法确定)', 'data': []}

    def add_domain_binding(self, hostname, domain):
        container = self._get_container_or_error(hostname)
        if not container: return {'code': 404, 'msg': '容器未找到'}
        logger.info(f"为容器 {hostname} 添加域名绑定: {domain}")
        limit = int(self._get_user_metadata(container, 'domain_acl_limit', 0))
        current_bindings_resp = self.list_domain_bindings(hostname)
        if current_bindings_resp['code'] == 200 and limit > 0:
            if len(current_bindings_resp.get('data', [])) >= limit:
                logger.warning(f"容器 {hostname} 已达到域名绑定数量上限 ({limit}条)")
                return {'code': 403, 'msg': f'已达到域名绑定数量上限 ({limit}条)'}
        domains_json = self._get_user_metadata(container, 'bound_domains', '[]')
        try:
            current_domains = json.loads(domains_json)
            if domain in current_domains:
                logger.warning(f"域名 {domain} 已绑定到容器 {hostname}")
                return {'code': 409, 'msg': f'域名 {domain} 已绑定到此容器'}
        except json.JSONDecodeError:
            current_domains = []
        container_ip = self._get_container_ip(container)
        if not container_ip:
            logger.error(f"为容器 {hostname} 添加域名绑定 {domain} 失败: 无法获取内部IP")
            return {'code': 500, 'msg': '无法获取容器内部IP地址'}
        success, msg = apache_manager.create_apache_vhost(domain, container_ip)
        if success:
            logger.info(f"容器 {hostname} 域名绑定 {domain} Apache配置成功: {msg}")
            if domain not in current_domains:
                current_domains.append(domain)
                self._set_user_metadata(container, 'bound_domains', json.dumps(current_domains))
            return {'code': 200, 'msg': msg}
        logger.error(f"容器 {hostname} 域名绑定 {domain} Apache配置失败: {msg}")
        return {'code': 500, 'msg': msg}

    def delete_domain_binding(self, hostname, domain):
        container = self._get_container_or_error(hostname)
        logger.info(f"删除域名绑定: {domain} (关联容器: {hostname})")
        success, msg = apache_manager.delete_apache_vhost(domain)
        if success:
            logger.info(f"域名绑定 {domain} Apache配置删除成功: {msg}")
            if container:
               domains_json = self._get_user_metadata(container, 'bound_domains', '[]')
               try:
                   current_domains = json.loads(domains_json)
                   if domain in current_domains:
                       current_domains.remove(domain)
                       self._set_user_metadata(container, 'bound_domains', json.dumps(current_domains))
                       logger.info(f"从容器 {hostname} 元数据中移除域名 {domain}")
               except json.JSONDecodeError:
                   logger.error(f"解析容器 {hostname} 的bound_domains元数据失败，无法移除 {domain}")
            return {'code': 200, 'msg': msg}
        logger.error(f"域名绑定 {domain} Apache配置删除失败: {msg}")
        return {'code': 500, 'msg': msg}
