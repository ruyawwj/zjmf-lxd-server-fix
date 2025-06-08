from pylxd import Client as LXDClient
from pylxd.exceptions import LXDAPIException, NotFound
from config_handler import app_config
import logging
import json
import subprocess
import os
import shlex
import random
import time
import datetime

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
            state_before = container.state()
            time.sleep(1)
            state = container.state()
            config = container.config
            cpu_cores = int(config.get('limits.cpu', '1'))
            cpu_usage_before = state_before.cpu.get('usage', 0)
            cpu_usage_after = state.cpu.get('usage', 0)
            cpu_usage_diff_ns = cpu_usage_after - cpu_usage_before
            cpu_percent = 0
            if cpu_cores > 0:
                total_possible_ns = 1_000_000_000 * cpu_cores
                cpu_percent = round((cpu_usage_diff_ns / total_possible_ns) * 100, 2)
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
            
            created_at_val = container.created_at
            if isinstance(created_at_val, datetime.datetime):
                created_at_str = created_at_val.isoformat()
            else:
                created_at_str = str(created_at_val) if created_at_val else None

            data = {
                'Hostname': hostname, 'Status': lxc_status,
                'UsedCPU': cpu_percent,
                'CPUCores': cpu_cores, # Added for lxdserver module
                'TotalRam': total_ram_mb, 'UsedRam': used_ram_mb,
                'TotalDisk': total_disk_mb, 'UsedDisk': used_disk_mb,
                'IP': self._get_container_ip(container) or 'N/A',
                'Bandwidth': flow_limit_gb,
                'UseBandwidth': used_flow_gb, # For lxdserver module
                'UseBandwidth_GB': used_flow_gb, # For new web UI
                'raw_lxd_info': {
                    'name': container.name,
                    'status': container.status,
                    'status_code': state.status_code,
                    'type': 'container',
                    'architecture': container.architecture,
                    'ephemeral': container.ephemeral,
                    'created_at': created_at_str,
                    'profiles': container.profiles,
                    'config': container.config,
                    'devices': container.devices,
                    'state': {
                         'cpu': state.cpu,
                         'disk': state.disk,
                         'memory': state.memory,
                         'network': state.network
                    },
                    'description': container.description
                }
            }
            return {'code': 200, 'msg': '获取成功', 'data': data}
        except LXDAPIException as e:
            logger.error(f"LXD API错误 (getinfo) for {hostname}: {e}")
            return {'code': 500, 'msg': f'LXD API错误 (getinfo): {e}'}
        except Exception as e:
            logger.error(f"获取信息时发生内部错误 for {hostname}: {str(e)}", exc_info=True)
            return {'code': 500, 'msg': f'获取信息时发生内部错误: {str(e)}'}

    def get_container_realtime_stats(self, hostname):
        container = self._get_container_or_error(hostname)
        if not container:
            return {'code': 404, 'msg': '容器未找到'}
        if container.status != 'Running':
            return {'code': 400, 'msg': '容器未运行'}
        try:
            state_before = container.state()
            time.sleep(1)
            state_after = container.state()
            cpu_cores = int(container.config.get('limits.cpu', '1'))
            cpu_usage_before = state_before.cpu.get('usage', 0)
            cpu_usage_after = state_after.cpu.get('usage', 0)
            cpu_usage_diff_ns = cpu_usage_after - cpu_usage_before
            cpu_percent = 0
            if cpu_cores > 0:
                total_possible_ns = 1_000_000_000 * cpu_cores
                cpu_percent = round((cpu_usage_diff_ns / total_possible_ns) * 100, 2)
            used_ram_mb = int(state_after.memory['usage'] / (1024*1024)) if state_after.memory and 'usage' in state_after.memory else 0
            used_disk_mb = int(state_after.disk['root']['usage'] / (1024*1024)) if state_after.disk and 'root' in state_after.disk and 'usage' in state_after.disk['root'] else 0
            bytes_rx_before, bytes_tx_before = 0, 0
            if state_before.network:
                for nic_data in state_before.network.values():
                    if 'counters' in nic_data:
                        bytes_rx_before += nic_data['counters'].get('bytes_received', 0)
                        bytes_tx_before += nic_data['counters'].get('bytes_sent', 0)
            bytes_rx_after, bytes_tx_after, bytes_total = 0, 0, 0
            if state_after.network:
                for nic_data in state_after.network.values():
                    if 'counters' in nic_data:
                        rx = nic_data['counters'].get('bytes_received', 0)
                        tx = nic_data['counters'].get('bytes_sent', 0)
                        bytes_rx_after += rx
                        bytes_tx_after += tx
                        bytes_total += rx + tx
            rx_speed_bps = bytes_rx_after - bytes_rx_before
            tx_speed_bps = bytes_tx_after - bytes_tx_before
            used_flow_gb = round(bytes_total / (1024*1024*1024), 2)
            stats = {
                'cpu_usage_percent': max(0, cpu_percent),
                'memory_usage_mb': used_ram_mb,
                'disk_usage_mb': used_disk_mb,
                'network_rx_kbps': round(rx_speed_bps / 1024, 2),
                'network_tx_kbps': round(tx_speed_bps / 1024, 2),
                'total_flow_used_gb': used_flow_gb,
            }
            return {'code': 200, 'msg': '获取成功', 'data': stats}
        except LXDAPIException as e:
            logger.error(f"LXD API错误 (get_container_realtime_stats) for {hostname}: {e}")
            return {'code': 500, 'msg': f'LXD API错误: {e}'}
        except Exception as e:
            logger.error(f"获取实时状态时发生内部错误 for {hostname}: {str(e)}", exc_info=True)
            return {'code': 500, 'msg': f'获取实时状态时发生内部错误: {str(e)}'}

    # === Restored functions from 'server old' for API compatibility ===

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

        container_to_cleanup_on_error = None
        try:
            logger.info(f"开始创建容器 {hostname} 使用配置: {container_config_obj}")
            container = self.client.containers.create(container_config_obj, wait=True)
            container_to_cleanup_on_error = container

            self._set_user_metadata(container, 'nat_acl_limit', params.get('ports', 0))
            self._set_user_metadata(container, 'flow_limit_gb', params.get('bandwidth', 0))
            self._set_user_metadata(container, 'disk_size_mb', params.get('disk', '1024'))
            logger.info(f"容器 {hostname} 配置完成，开始启动...")
            container.start(wait=True)
            logger.info(f"容器 {hostname} 启动成功")

            logger.info(f"容器 {hostname} 已启动，准备设置初始密码...")
            time.sleep(10)

            new_password = params.get('password')
            if not new_password:
                logger.error(f"为容器 {hostname} 设置初始密码失败：未提供密码。")
            else:
                user_for_password = app_config.default_container_user
                try:
                    logger.info(f"为容器 {hostname} 的用户 {user_for_password} 设置初始密码 (使用 bash -c 'echo ... | chpasswd')")
                    escaped_new_password = shlex.quote(new_password)
                    command_to_execute_in_bash = f"echo '{user_for_password}:{escaped_new_password}' | chpasswd"
                    logger.debug(f"在容器内执行命令: bash -c \"{command_to_execute_in_bash}\"")

                    current_status_check = container.state().status
                    if current_status_check.lower() != 'running':
                        logger.error(f"容器 {hostname} 未处于运行状态 (当前状态: {current_status_check})，无法设置初始密码。")
                    else:
                        exit_code, stdout, stderr = container.execute(['bash', '-c', command_to_execute_in_bash])
                        if exit_code == 0:
                            logger.info(f"容器 {hostname} 初始密码使用 bash -c 'echo ... | chpasswd' 设置成功")
                        else:
                            err_msg_stdout = stdout.decode('utf-8', errors='ignore').strip() if stdout else ""
                            err_msg_stderr = stderr.decode('utf-8', errors='ignore').strip() if stderr else ""
                            full_err_msg = []
                            if err_msg_stdout: full_err_msg.append(f"STDOUT: {err_msg_stdout}")
                            if err_msg_stderr: full_err_msg.append(f"STDERR: {err_msg_stderr}")
                            combined_err_msg = "; ".join(full_err_msg) if full_err_msg else "命令执行失败，但未提供具体错误信息"
                            logger.error(f"容器 {hostname} 设置初始密码失败 (exit_code: {exit_code}): {combined_err_msg}")
                except LXDAPIException as e_passwd:
                    logger.error(f"为容器 {hostname} 设置初始密码时发生LXD API错误: {e_passwd}")
                except Exception as e_passwd_generic:
                    logger.error(f"为容器 {hostname} 设置初始密码时发生未知错误: {e_passwd_generic}", exc_info=True)
            try:
                ssh_external_port_min = 10000
                ssh_external_port_max = 65535
                random_ssh_dport = random.randint(ssh_external_port_min, ssh_external_port_max)
                logger.info(f"尝试为容器 {hostname} 自动添加 SSH (端口 22) 的 NAT 规则，使用外部端口 {random_ssh_dport}")

                container_ip_for_nat = None
                nat_add_attempts = 0
                while not container_ip_for_nat and nat_add_attempts < 3:
                    container_ip_for_nat = self._get_container_ip(container)
                    if container_ip_for_nat: break
                    logger.warning(f"为容器 {hostname} 获取IP失败 (尝试 {nat_add_attempts+1}/3)，等待后重试...")
                    time.sleep(5)
                    nat_add_attempts += 1

                if not container_ip_for_nat:
                    logger.error(f"为容器 {hostname} 自动添加 SSH NAT 规则失败：多次尝试后仍无法获取容器IP地址。")
                else:
                    add_ssh_rule_result = self.add_nat_rule_via_iptables(hostname, 'tcp', str(random_ssh_dport), '22')
                    if add_ssh_rule_result.get('code') == 200:
                        logger.info(f"成功为容器 {hostname} 自动添加 SSH NAT 规则: 外部端口 {random_ssh_dport} -> 内部端口 22")
                    elif add_ssh_rule_result.get('code') == 409:
                        logger.warning(f"尝试为容器 {hostname} 自动添加 SSH NAT 规则失败：外部端口 {random_ssh_dport} 已被此容器的其他规则使用。可尝试重新创建或手动添加其他端口。")
                    else:
                        logger.error(f"为容器 {hostname} 自动添加 SSH NAT 规则失败。外部端口: {random_ssh_dport}, 原因: {add_ssh_rule_result.get('msg')}")
            except Exception as e_ssh_nat:
                logger.error(f"为容器 {hostname} 自动添加 SSH NAT 规则时发生异常: {str(e_ssh_nat)}", exc_info=True)

            return {'code': 200, 'msg': '容器创建成功'}
        except (LXDAPIException, Exception) as e:
            error_type_msg = "LXD API错误" if isinstance(e, LXDAPIException) else "内部错误"
            logger.error(f"创建容器 {hostname} 过程中发生{error_type_msg}: {str(e)}", exc_info=True)
            if container_to_cleanup_on_error and self.client.containers.exists(container_to_cleanup_on_error.name):
                 try:
                     logger.info(f"创建过程中发生错误，尝试删除可能已部分创建的容器 {container_to_cleanup_on_error.name}")
                     current_state = container_to_cleanup_on_error.state()
                     if current_state.status and current_state.status.lower() == 'running':
                         container_to_cleanup_on_error.stop(wait=True)
                     container_to_cleanup_on_error.delete(wait=True)
                     logger.info(f"部分创建的容器 {container_to_cleanup_on_error.name} 已删除。")
                 except Exception as e_cleanup:
                     logger.error(f"尝试清理部分创建的容器 {container_to_cleanup_on_error.name} 时失败: {e_cleanup}")
            return {'code': 500, 'msg': f'{error_type_msg} (create): {str(e)}'}

    def add_nat_rule_via_iptables(self, hostname, dtype, dport, sport):
        container = self._get_container_or_error(hostname)
        if not container: return {'code': 404, 'msg': '容器未找到'}

        logger.info(f"为容器 {hostname} 通过iptables添加NAT规则: {dtype} {dport} -> {sport}")

        limit = int(self._get_user_metadata(container, 'nat_acl_limit', 0))
        rules_metadata = _load_iptables_rules_metadata()
        current_host_rules_count = sum(1 for r in rules_metadata if r.get('hostname') == hostname)

        is_ssh_rule = (str(sport) == '22' and dtype.lower() == 'tcp')
        if not is_ssh_rule and limit > 0 and current_host_rules_count >= limit :
            logger.warning(f"容器 {hostname} 已达到iptables NAT规则数量上限 ({limit}条)")
            return {'code': 403, 'msg': f'已达到NAT规则数量上限 ({limit}条)'}
        elif is_ssh_rule and limit > 0 and current_host_rules_count >= limit:
            logger.info(f"允许为容器 {hostname} 添加SSH (端口22) 的NAT规则，即使已达到或超过常规端口转发上限 ({current_host_rules_count}/{limit})。")

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
        if not main_interface and not getattr(app_config, 'skip_masquerade', False):
             logger.error("配置文件中缺少 main_interface (主网卡名) for iptables MASQUERADE rule, 或设置 skip_masquerade: true")
             return {'code': 500, 'msg': '服务器配置错误：缺少主网卡信息用于NAT'}


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

        if main_interface and not getattr(app_config, 'skip_masquerade', False):
            masquerade_args = [
                '-t', 'nat', '-A', 'POSTROUTING',
                '-s', container_ip,
                '-o', main_interface,
                '-j', 'MASQUERADE',
                '-m', 'comment', '--comment', f'{rule_comment}_masq'
            ]
            success_masq, msg_masq = self._run_shell_command_for_iptables(masquerade_args)
            if not success_masq:
                dnat_del_args = ['-t', 'nat', '-D', 'PREROUTING', '-d', host_listen_ip, '-p', dtype.lower(), '--dport', str(dport), '-j', 'DNAT', '--to-destination', f"{container_ip}:{sport}", '-m', 'comment', '--comment', rule_comment]
                self._run_shell_command_for_iptables(dnat_del_args)
                logger.error(f"添加MASQUERADE规则失败后，尝试回滚DNAT规则 for {rule_comment}")
                return {'code': 500, 'msg': f"添加MASQUERADE规则失败: {msg_masq}"}

        new_rule_meta = {
            'hostname': hostname, 'dtype': dtype.lower(), 'dport': str(dport),
            'sport': str(sport), 'container_ip': container_ip, 'rule_id': rule_comment
        }
        rules_metadata.append(new_rule_meta)
        _save_iptables_rules_metadata(rules_metadata)

        logger.info(f"容器 {hostname} 通过iptables添加DNAT规则成功 (MASQUERADE规则根据配置添加)")
        return {'code': 200, 'msg': 'NAT规则(iptables)添加成功'}

    # === End of restored functions ===

    def delete_container(self, hostname):
        container = self._get_container_or_error(hostname)
        if not container: return {'code': 404, 'msg': '容器未找到'}
        try:
            logger.info(f"开始删除容器 {hostname}")

            logger.info(f"删除容器 {hostname} 前，清理其所有 NAT 规则")
            rules_metadata_snapshot = _load_iptables_rules_metadata()
            rules_for_this_host_to_delete = [
                rule for rule in rules_metadata_snapshot if rule.get('hostname') == hostname
            ]

            if not rules_for_this_host_to_delete:
                logger.info(f"容器 {hostname} 没有找到关联的 NAT 规则。")
            else:
                for rule_meta_to_delete in rules_for_this_host_to_delete:
                    logger.info(f"准备删除容器 {hostname} 的iptables规则: {rule_meta_to_delete}")
                    delete_attempt_result = self.delete_nat_rule_via_iptables(
                        hostname,
                        rule_meta_to_delete['dtype'],
                        rule_meta_to_delete['dport'],
                        rule_meta_to_delete['sport'],
                        container_ip_at_creation_time=rule_meta_to_delete.get('container_ip')
                    )
                    if delete_attempt_result.get('code') == 200:
                        logger.info(f"成功删除 NAT 规则: {rule_meta_to_delete} for {hostname}")
                    else:
                        logger.warning(f"删除 NAT 规则 {rule_meta_to_delete} for {hostname} 可能失败. 原因: {delete_attempt_result.get('msg')}")

            if container.status == 'Running':
                logger.info(f"容器 {hostname} 正在运行，先停止...")
                container.stop(wait=True)

            container.delete(wait=True)
            logger.info(f"容器 {hostname} 删除成功")

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
        if not container:
            return {'code': 404, 'msg': '容器未找到'}

        current_status_check = container.state().status
        if current_status_check.lower() != 'running':
            logger.warning(f"尝试为容器 {hostname} 修改密码，但容器未运行 (状态: {current_status_check})")
            return {'code': 400, 'msg': f'容器未运行 (状态: {current_status_check})'}
        try:
            user = app_config.default_container_user
            logger.info(f"开始为容器 {hostname} 的用户 {user} 修改密码 (使用 bash -c 'echo ... | chpasswd')")

            escaped_new_password = shlex.quote(new_password)
            command_to_execute_in_bash = f"echo '{user}:{escaped_new_password}' | chpasswd"

            logger.debug(f"在容器内执行命令: bash -c \"{command_to_execute_in_bash}\"")
            exit_code, stdout, stderr = container.execute(['bash', '-c', command_to_execute_in_bash])

            if exit_code == 0:
                logger.info(f"容器 {hostname} 密码使用 bash -c 'echo ... | chpasswd' 修改成功")
                return {'code': 200, 'msg': '密码修改成功'}
            else:
                err_msg_stdout = stdout.decode('utf-8', errors='ignore').strip() if stdout else ""
                err_msg_stderr = stderr.decode('utf-8', errors='ignore').strip() if stderr else ""
                full_err_msg = []
                if err_msg_stdout: full_err_msg.append(f"STDOUT: {err_msg_stdout}")
                if err_msg_stderr: full_err_msg.append(f"STDERR: {err_msg_stderr}")
                combined_err_msg = "; ".join(full_err_msg) if full_err_msg else "命令执行失败，但未提供具体错误信息"
                logger.error(f"容器 {hostname} 使用 bash -c 'echo ... | chpasswd' 修改密码失败 (exit_code: {exit_code}): {combined_err_msg}")
                return {'code': 500, 'msg': f'密码修改失败: {combined_err_msg}'}
        except LXDAPIException as e:
            logger.error(f"LXD API错误 (change password for {hostname}): {e}")
            return {'code': 500, 'msg': f'LXD API错误 (password): {e}'}
        except Exception as e:
            logger.error(f"修改密码 for {hostname} 时发生内部错误: {str(e)}", exc_info=True)
            return {'code': 500, 'msg': f'修改密码时发生内部错误: {str(e)}'}

    def reinstall_container(self, hostname, new_os_alias, new_password):
        container = self._get_container_or_error(hostname)
        if not container: return {'code': 404, 'msg': '容器未找到'}
        logger.info(f"开始重装容器 {hostname} 为系统 {new_os_alias}")

        original_config_keys = ['limits.cpu', 'limits.memory', 'user.nat_acl_limit', 'user.flow_limit_gb', 'user.disk_size_mb']
        original_devices_to_keep_config = ['eth0']

        preserved_config = {k: v for k, v in container.config.items() if k in original_config_keys}
        preserved_devices = {dev_name: dev_data for dev_name, dev_data in container.devices.items() if dev_name in original_devices_to_keep_config}
        new_root_size = self._get_user_metadata(container, 'disk_size_mb', '1024') + "MB"

        try:
            if container.status == 'Running':
                logger.info(f"容器 {hostname}正在运行，重装前先停止...")
                container.stop(wait=True)

            logger.info(f"重装容器 {hostname} 前，清理其所有 NAT 规则")
            rules_metadata_snapshot_reinstall = _load_iptables_rules_metadata()
            rules_for_this_host_to_delete_reinstall = [
                rule for rule in rules_metadata_snapshot_reinstall if rule.get('hostname') == hostname
            ]

            if not rules_for_this_host_to_delete_reinstall:
                logger.info(f"容器 {hostname} (重装前) 没有找到关联的 NAT 规则。")
            else:
                for rule_meta_to_delete in rules_for_this_host_to_delete_reinstall:
                    logger.info(f"准备删除容器 {hostname} (重装前) 的iptables规则: {rule_meta_to_delete}")
                    delete_attempt_result = self.delete_nat_rule_via_iptables(
                        hostname,
                        rule_meta_to_delete['dtype'],
                        rule_meta_to_delete['dport'],
                        rule_meta_to_delete['sport'],
                        container_ip_at_creation_time=rule_meta_to_delete.get('container_ip')
                    )
                    if delete_attempt_result.get('code') == 200:
                        logger.info(f"成功删除 NAT 规则 (重装前): {rule_meta_to_delete} for {hostname}")
                    else:
                        logger.warning(f"删除 NAT 规则 (重装前) {rule_meta_to_delete} for {hostname} 可能失败. 原因: {delete_attempt_result.get('msg')}")

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
            logger.info(f"容器 {hostname} 重装并启动成功.")

            logger.info(f"重装后的容器 {hostname} 已启动，准备设置密码...")
            time.sleep(10)

            if not new_password:
                logger.error(f"为重装后的容器 {hostname} 设置密码失败：未提供密码。")
            else:
                user_for_password = app_config.default_container_user
                try:
                    logger.info(f"为重装后的容器 {hostname} 的用户 {user_for_password} 设置密码 (使用 bash -c 'echo ... | chpasswd')")
                    escaped_new_password = shlex.quote(new_password)
                    command_to_execute_in_bash = f"echo '{user_for_password}:{escaped_new_password}' | chpasswd"
                    logger.debug(f"在容器内执行命令: bash -c \"{command_to_execute_in_bash}\"")

                    current_status_check = new_container.state().status
                    if current_status_check.lower() != 'running':
                        logger.error(f"重装后的容器 {hostname} 未处于运行状态 (当前状态: {current_status_check})，无法设置密码。")
                    else:
                        exit_code, stdout, stderr = new_container.execute(['bash', '-c', command_to_execute_in_bash])
                        if exit_code == 0:
                            logger.info(f"重装后的容器 {hostname} 密码使用 bash -c 'echo ... | chpasswd' 设置成功")
                        else:
                            err_msg_stdout = stdout.decode('utf-8', errors='ignore').strip() if stdout else ""
                            err_msg_stderr = stderr.decode('utf-8', errors='ignore').strip() if stderr else ""
                            full_err_msg = []
                            if err_msg_stdout: full_err_msg.append(f"STDOUT: {err_msg_stdout}")
                            if err_msg_stderr: full_err_msg.append(f"STDERR: {err_msg_stderr}")
                            combined_err_msg = "; ".join(full_err_msg) if full_err_msg else "命令执行失败，但未提供具体错误信息"
                            logger.error(f"重装后的容器 {hostname} 设置密码失败 (exit_code: {exit_code}): {combined_err_msg}")
                except LXDAPIException as e_passwd:
                    logger.error(f"为重装后的容器 {hostname} 设置密码时发生LXD API错误: {e_passwd}")
                except Exception as e_passwd_generic:
                    logger.error(f"为重装后的容器 {hostname} 设置密码时发生未知错误: {e_passwd_generic}", exc_info=True)

            try:
                ssh_external_port_min_reinstall = 10000
                ssh_external_port_max_reinstall = 65535
                random_ssh_dport_reinstall = random.randint(ssh_external_port_min_reinstall, ssh_external_port_max_reinstall)
                logger.info(f"尝试为重装后的容器 {hostname} 自动添加 SSH (端口 22) 的 NAT 规则，使用外部端口 {random_ssh_dport_reinstall}")

                container_ip_for_nat_reinstall = None
                nat_add_attempts_reinstall = 0
                while not container_ip_for_nat_reinstall and nat_add_attempts_reinstall < 3:
                    container_ip_for_nat_reinstall = self._get_container_ip(new_container)
                    if container_ip_for_nat_reinstall: break
                    logger.warning(f"为重装后的容器 {hostname} 获取IP失败 (尝试 {nat_add_attempts_reinstall+1}/3)，等待后重试...")
                    time.sleep(5)
                    nat_add_attempts_reinstall +=1

                if not container_ip_for_nat_reinstall:
                     logger.error(f"为重装后的容器 {hostname} 自动添加 SSH NAT 规则失败：多次尝试后仍无法获取容器IP地址。")
                else:
                    add_ssh_rule_result_reinstall = self.add_nat_rule_via_iptables(new_container.name, 'tcp', str(random_ssh_dport_reinstall), '22')
                    if add_ssh_rule_result_reinstall.get('code') == 200:
                        logger.info(f"成功为重装后的容器 {hostname} 自动添加 SSH NAT 规则: 外部端口 {random_ssh_dport_reinstall} -> 内部端口 22")
                    elif add_ssh_rule_result_reinstall.get('code') == 409:
                         logger.warning(f"尝试为重装后的容器 {hostname} 自动添加 SSH NAT 规则失败：外部端口 {random_ssh_dport_reinstall} 已被此容器的其他规则使用。可尝试手动添加其他端口。")
                    else:
                        logger.error(f"为重装后的容器 {hostname} 自动添加 SSH NAT 规则失败。外部端口: {random_ssh_dport_reinstall}, 原因: {add_ssh_rule_result_reinstall.get('msg')}")
            except Exception as e_ssh_nat_reinstall:
                logger.error(f"为重装后的容器 {hostname} 自动添加 SSH NAT 规则时发生异常: {str(e_ssh_nat_reinstall)}", exc_info=True)

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

    def delete_nat_rule_via_iptables(self, hostname, dtype, dport, sport, container_ip_at_creation_time=None):
        logger.info(f"为容器 {hostname} 通过iptables删除NAT规则: {dtype} {dport} -> {sport} (原始IP: {container_ip_at_creation_time})")
        host_listen_ip = app_config.nat_listen_ip
        rules_metadata = _load_iptables_rules_metadata()

        rule_to_delete_meta = None
        rule_comment_to_use = f'lxd_controller_nat_{hostname}_{dtype.lower()}_{dport}'

        for idx, rule_meta_item in enumerate(rules_metadata):
            if rule_meta_item.get('hostname') == hostname and \
               rule_meta_item.get('dtype', '').lower() == dtype.lower() and \
               str(rule_meta_item.get('dport')) == str(dport) and \
               str(rule_meta_item.get('sport')) == str(sport) :
                rule_to_delete_meta = rule_meta_item
                rule_comment_to_use = rule_meta_item.get('rule_id', rule_comment_to_use)
                if not container_ip_at_creation_time:
                    container_ip_at_creation_time = rule_meta_item.get('container_ip')
                break

        effective_container_ip = container_ip_at_creation_time

        if not effective_container_ip and not rule_to_delete_meta :
            container = self._get_container_or_error(hostname)
            if container :
                current_status_check = container.state().status
                if current_status_check.lower() == 'running':
                    effective_container_ip = self._get_container_ip(container)
                    logger.info(f"无法从元数据或参数获取IP，使用当前运行容器IP: {effective_container_ip} for {hostname} {dtype} {dport}")

        if not effective_container_ip:
            logger.error(f"删除iptables规则失败: 无法确定容器IP for {hostname} {dtype} {dport} -> {sport}")
            if rule_to_delete_meta:
                 rules_metadata_after_delete = [r for r in rules_metadata if r.get('rule_id') != rule_comment_to_use]
                 if len(rules_metadata_after_delete) < len(rules_metadata):
                     _save_iptables_rules_metadata(rules_metadata_after_delete)
                     logger.info(f"从元数据中移除了 {rule_comment_to_use} (由于无法获取IP，仅操作元数据)")
                     return {'code': 200, 'msg': 'NAT规则元数据已移除，但因无法获取IP，iptables规则可能未删除'}
            return {'code': 500, 'msg': '删除iptables规则失败: 无法确定容器IP且元数据中未找到特定规则信息'}

        dnat_del_args = [
            '-t', 'nat', '-D', 'PREROUTING',
            '-d', host_listen_ip,
            '-p', dtype.lower(), '--dport', str(dport),
            '-j', 'DNAT', '--to-destination', f"{effective_container_ip}:{sport}",
            '-m', 'comment', '--comment', rule_comment_to_use
        ]
        success_dnat, msg_dnat = self._run_shell_command_for_iptables(dnat_del_args)

        rule_deleted_from_iptables_ok = False
        if success_dnat:
            rule_deleted_from_iptables_ok = True
            logger.info(f"DNAT规则 (comment: {rule_comment_to_use}) iptables删除成功")
        else:
            logger.warning(f"删除DNAT规则 (comment: {rule_comment_to_use}) 的iptables命令执行失败 (可能规则已不存在): {msg_dnat}")

        main_interface = getattr(app_config, 'main_interface', None)
        if main_interface and not getattr(app_config, 'skip_masquerade', False):
            masquerade_del_args = [
                '-t', 'nat', '-D', 'POSTROUTING',
                '-s', effective_container_ip,
                '-o', main_interface,
                '-j', 'MASQUERADE',
                '-m', 'comment', '--comment', f'{rule_comment_to_use}_masq'
            ]
            success_masq, msg_masq = self._run_shell_command_for_iptables(masquerade_del_args)
            if success_masq:
                logger.info(f"MASQUERADE规则 (comment: {rule_comment_to_use}_masq) iptables删除成功")
            else:
                logger.warning(f"删除MASQUERADE规则 (comment: {rule_comment_to_use}_masq) 的iptables命令执行失败 (可能规则已不存在): {msg_masq}")

        final_rules_to_keep = []
        deleted_from_meta = False
        if rule_to_delete_meta:
            for r_meta in rules_metadata:
                if r_meta.get('rule_id') == rule_comment_to_use:
                    deleted_from_meta = True
                else:
                    final_rules_to_keep.append(r_meta)
        else:
            logger.warning(f"尝试从元数据删除规则 {rule_comment_to_use}，但未在元数据中精确定位到此规则。将基于参数尝试过滤。")
            for r_meta in rules_metadata:
                if not (r_meta.get('hostname') == hostname and \
                        r_meta.get('dtype', '').lower() == dtype.lower() and \
                        str(r_meta.get('dport')) == str(dport) and \
                        str(r_meta.get('sport')) == str(sport)):
                    final_rules_to_keep.append(r_meta)
                else:
                    deleted_from_meta = True

        if deleted_from_meta:
            _save_iptables_rules_metadata(final_rules_to_keep)
            logger.info(f"从元数据中移除规则: {rule_comment_to_use if rule_to_delete_meta else '匹配参数的规则'}")
        else:
             logger.info(f"元数据中未找到与 {rule_comment_to_use} (或给定参数) 完全匹配的规则，无需从元数据删除。")

        final_check_metadata = _load_iptables_rules_metadata()
        still_in_meta = any(r.get('rule_id') == rule_comment_to_use for r in final_check_metadata) or \
                        any(r.get('hostname') == hostname and r.get('dtype','').lower() == dtype.lower() and str(r.get('dport')) == str(dport) and str(r.get('sport')) == str(sport) for r in final_check_metadata)


        if not still_in_meta:
             logger.info(f"规则 {rule_comment_to_use} 已成功从元数据中移除或之前不存在。")
             return {'code': 200, 'msg': 'NAT规则(iptables)删除尝试完成'}
        else:
             logger.warning(f"规则 {rule_comment_to_use} 在尝试删除后似乎仍在元数据中。iptables删除命令状态: {success_dnat}")
             return {'code': 500, 'msg': 'NAT规则(iptables)删除尝试部分失败，规则可能仍在元数据或iptables中'}