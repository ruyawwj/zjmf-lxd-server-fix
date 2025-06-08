import os
from flask import Flask, render_template, jsonify, request, session, redirect, url_for
from functools import wraps
import logging
import datetime

from config_handler import app_config
from lxc_manager import LXCManager, _load_iptables_rules_metadata

app = Flask(__name__, template_folder='templates', static_folder='static')
app.secret_key = os.urandom(24)

logging.basicConfig(level=getattr(logging, app_config.log_level, logging.INFO),
                    format='%(asctime)s %(levelname)s: %(message)s [%(filename)s:%(lineno)d]',
                    datefmt='%Y-%m-%d %H:%M:%S')
logger = logging.getLogger(__name__)

try:
    lxc = LXCManager()
except RuntimeError as e:
    logger.critical(f"无法连接到LXD，程序中止。错误: {e}")
    exit(1)

# === Authentication for Web UI ===
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

# === Authentication for external API (lxdserver.php) ===
def api_key_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        provided_key = request.headers.get('apikey')
        if provided_key and provided_key == app_config.token:
            return f(*args, **kwargs)
        else:
            logger.warning(f"API认证失败: 无效的API Key from {request.remote_addr}.提供的Key: '{provided_key}'")
            return jsonify({'code': 401, 'msg': '认证失败或API密钥无效'}), 401
    return decorated_function

def adapt_response(lxd_response, success_status='success', error_status='error'):
    if lxd_response.get('code') == 200:
        return {'status': success_status, 'message': lxd_response.get('msg', '操作成功')}
    else:
        return {'status': error_status, 'message': lxd_response.get('msg', '操作失败')}

# === Routes for Web UI ===

@app.route('/login', methods=['GET', 'POST'])
def login():
    template_context = {
        'session': session,
        'incus_error': (False, None),
        'image_error': (False, None),
        'storage_error': (False, None),
        'containers': [],
        'images': [],
        'available_pools': [],
        'login_error': None
    }

    if request.method == 'POST':
        if request.form.get('password') == app_config.token:
            session['logged_in'] = True
            next_url = request.args.get('next')
            return redirect(next_url or url_for('index'))
        else:
            template_context['login_error'] = "密码错误"
            return render_template('index.html', **template_context)
            
    return render_template('index.html', **template_context)

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    incus_error = (False, None)
    containers_list = []
    try:
        fingerprint_to_alias_map = {}
        all_images_for_map = lxc.client.images.all()
        for img in all_images_for_map:
            if img.aliases:
                fingerprint_to_alias_map[img.fingerprint] = img.aliases[0]['name']

        all_containers = lxc.client.containers.all()
        for c in all_containers:
            info_res = lxc.get_container_info(c.name)
            data = info_res.get('data', {})

            container_fingerprint = c.config.get('volatile.base_image')
            image_source = "N/A"
            if container_fingerprint:
                image_source = fingerprint_to_alias_map.get(
                    container_fingerprint,
                    c.config.get('image.description', container_fingerprint)
                )
            else:
                image_source = c.config.get('image.description', 'N/A')
            
            created_at_val = c.created_at
            if isinstance(created_at_val, datetime.datetime):
                created_at_str = created_at_val.isoformat()
            else:
                created_at_str = str(created_at_val) if created_at_val else 'N/A'

            containers_list.append({
                'name': c.name,
                'status': c.status,
                'ip': data.get('IP', 'N/A'),
                'image_source': image_source,
                'created_at': created_at_str,
                'cpu_usage': data.get('UsedCPU', '-'),
                'mem_usage': data.get('UsedRam', '-'),
                'disk_usage': data.get('UsedDisk', '-'),
                'total_flow': data.get('UseBandwidth_GB', '-'),
                'mem_total': data.get('TotalRam', 0),
                'disk_total': data.get('TotalDisk', 0),
                'flow_limit': data.get('Bandwidth', 0)
            })
    except Exception as e:
        logger.error(f"获取容器列表失败: {e}", exc_info=True)
        incus_error = (True, str(e))

    image_error = (False, None)
    available_images = []
    try:
        all_images = lxc.client.images.all()
        for img in all_images:
            if not img.aliases: continue
            alias_name = img.aliases[0]['name']
            desc = img.properties.get('description', '无描述')
            available_images.append({'name': alias_name, 'description': f"{alias_name} ({desc})"})
    except Exception as e:
        logger.error(f"获取镜像列表失败: {e}")
        image_error = (True, str(e))

    storage_error = (False, None)
    available_pools = []
    try:
        all_pools = lxc.client.storage_pools.all()
        available_pools = [p.name for p in all_pools]
    except Exception as e:
        logger.error(f"获取存储池列表失败: {e}")
        storage_error = (True, str(e))

    return render_template('index.html',
                           containers=containers_list,
                           images=available_images,
                           available_pools=available_pools,
                           incus_error=incus_error,
                           image_error=image_error,
                           storage_error=storage_error,
                           session=session)

@app.route('/container/<name>/action', methods=['POST'])
@login_required
def container_action(name):
    action = request.form.get('action')
    logger.info(f"WebUI请求对 {name} 执行操作: {action}")
    if action == 'start':
        result = lxc.start_container(name)
    elif action == 'stop':
        result = lxc.stop_container(name)
    elif action == 'restart':
        result = lxc.restart_container(name)
    elif action == 'delete':
        result = lxc.delete_container(name)
    else:
        result = {'code': 400, 'msg': '无效操作'}
    return jsonify(adapt_response(result))

@app.route('/container/<name>/info')
@login_required
def container_info(name):
    logger.info(f"WebUI请求获取 {name} 的信息")
    res = lxc.get_container_info(name)
    if res['code'] != 200:
        return jsonify({'status': 'NotFound', 'message': res['msg']}), 404

    lxc_data = res.get('data', {})
    raw_data = lxc_data.get('raw_lxd_info', {})
    adapted_info = {
        'name': raw_data.get('name'),
        'status': raw_data.get('status'),
        'status_code': raw_data.get('status_code'),
        'type': raw_data.get('type'),
        'architecture': raw_data.get('architecture'),
        'ephemeral': raw_data.get('ephemeral'),
        'created_at': raw_data.get('created_at'),
        'profiles': raw_data.get('profiles', []),
        'config': raw_data.get('config', {}),
        'devices': raw_data.get('devices', {}),
        'state': raw_data.get('state', {}),
        'description': raw_data.get('description'),
        'ip': lxc_data.get('IP'),
        'total_ram_mb': lxc_data.get('TotalRam', 0),
        'total_disk_mb': lxc_data.get('TotalDisk', 0),
        'flow_limit_gb': lxc_data.get('Bandwidth', 0),
        'live_data_available': raw_data.get('status') == 'Running',
        'message': '数据来自LXD实时信息'
    }
    return jsonify(adapted_info)

@app.route('/container/<name>/stats')
@login_required
def container_stats(name):
    logger.debug(f"WebUI请求获取 {name} 的实时状态")
    res = lxc.get_container_realtime_stats(name)
    if res['code'] != 200:
        return jsonify({'status': 'error', 'message': res['msg']}), res.get('code', 500)
    return jsonify(res['data'])

@app.route('/container/<name>/nat_rules', methods=['GET'])
@login_required
def list_nat_rules(name):
    logger.info(f"WebUI请求获取 {name} 的NAT规则")
    res = lxc.list_nat_rules(name)
    if res['code'] != 200:
        return jsonify({'status': 'error', 'message': res['msg']}), 500

    adapted_rules = []
    for rule in res.get('data', []):
        adapted_rules.append({
            'id': rule.get('ID'),
            'host_port': rule.get('Dport'),
            'container_port': rule.get('Sport'),
            'protocol': rule.get('Dtype').lower(),
            'ip_at_creation': 'N/A',
            'created_at': datetime.datetime.now().isoformat()
        })
    return jsonify({'status': 'success', 'rules': adapted_rules})

@app.route('/container/nat_rule/<rule_id>', methods=['DELETE'])
@login_required
def delete_nat_rule(rule_id):
    logger.info(f"WebUI请求删除NAT规则ID: {rule_id}")
    rules_metadata = _load_iptables_rules_metadata()
    rule_to_delete = next((rule for rule in rules_metadata if rule.get('rule_id') == rule_id), None)

    if not rule_to_delete:
        return jsonify({'status': 'error', 'message': '未在元数据中找到该规则ID'}), 404

    hostname = rule_to_delete.get('hostname')
    dtype = rule_to_delete.get('dtype')
    dport = rule_to_delete.get('dport')
    sport = rule_to_delete.get('sport')
    ip_at_creation = rule_to_delete.get('container_ip')

    result = lxc.delete_nat_rule_via_iptables(hostname, dtype, dport, sport, ip_at_creation)
    return jsonify(adapt_response(result))

# === Routes for External API (lxdserver.php) ===

@app.route('/api/check', methods=['GET'])
@api_key_required
def api_check():
    logger.info(f"API /api/check a called successfully from {request.remote_addr}")
    return jsonify({'code': 200, 'msg': 'API连接正常'})

@app.route('/api/getinfo', methods=['GET'])
@api_key_required
def api_getinfo():
    hostname = request.args.get('hostname')
    if not hostname:
        logger.warning("API /api/getinfo 调用缺少 hostname 参数")
        return jsonify({'code': 400, 'msg': '缺少hostname参数'}), 400
    logger.info(f"API请求getinfo for: {hostname}")
    return jsonify(lxc.get_container_info(hostname))

@app.route('/api/create', methods=['POST'])
@api_key_required
def api_create():
    try:
        payload = request.json
        if not payload or not payload.get('hostname'):
            logger.warning(f"API /api/create 调用请求体无效或缺少hostname. Payload: {payload}")
            return jsonify({'code': 400, 'msg': '无效的请求体或缺少hostname'}), 400
        logger.info(f"API请求create for: {payload.get('hostname')}")
        return jsonify(lxc.create_container(payload))
    except Exception as e:
        logger.error(f"处理 /api/create 时发生意外错误: {e}", exc_info=True)
        return jsonify({'code': 500, 'msg': '服务器内部错误'}), 500


@app.route('/api/delete', methods=['GET'])
@api_key_required
def api_delete():
    hostname = request.args.get('hostname')
    if not hostname:
        logger.warning("API /api/delete 调用缺少 hostname 参数")
        return jsonify({'code': 400, 'msg': '缺少hostname参数'}), 400
    logger.info(f"API请求delete for: {hostname}")
    return jsonify(lxc.delete_container(hostname))

@app.route('/api/boot', methods=['GET'])
@api_key_required
def api_boot():
    hostname = request.args.get('hostname')
    if not hostname:
        logger.warning("API /api/boot 调用缺少 hostname 参数")
        return jsonify({'code': 400, 'msg': '缺少hostname参数'}), 400
    logger.info(f"API请求boot for: {hostname}")
    return jsonify(lxc.start_container(hostname))

@app.route('/api/stop', methods=['GET'])
@api_key_required
def api_stop():
    hostname = request.args.get('hostname')
    if not hostname:
        logger.warning("API /api/stop 调用缺少 hostname 参数")
        return jsonify({'code': 400, 'msg': '缺少hostname参数'}), 400
    logger.info(f"API请求stop for: {hostname}")
    return jsonify(lxc.stop_container(hostname))

@app.route('/api/reboot', methods=['GET'])
@api_key_required
def api_reboot():
    hostname = request.args.get('hostname')
    if not hostname:
        logger.warning("API /api/reboot 调用缺少 hostname 参数")
        return jsonify({'code': 400, 'msg': '缺少hostname参数'}), 400
    logger.info(f"API请求reboot for: {hostname}")
    return jsonify(lxc.restart_container(hostname))

@app.route('/api/password', methods=['POST'])
@api_key_required
def api_password():
    try:
        payload = request.json
        hostname = payload.get('hostname')
        new_pass = payload.get('password')
        if not hostname or not new_pass:
            logger.warning(f"API /api/password 调用缺少hostname或password参数. Payload: {payload}")
            return jsonify({'code': 400, 'msg': '缺少hostname或password参数'}), 400
        logger.info(f"API请求password change for: {hostname}")
        return jsonify(lxc.change_password(hostname, new_pass))
    except Exception as e:
        logger.error(f"处理 /api/password 时发生意外错误: {e}", exc_info=True)
        return jsonify({'code': 500, 'msg': '服务器内部错误'}), 500

@app.route('/api/reinstall', methods=['POST'])
@api_key_required
def api_reinstall():
    try:
        payload = request.json
        hostname = payload.get('hostname')
        new_os = payload.get('system')
        new_password = payload.get('password')
        if not all([hostname, new_os, new_password]):
            logger.warning(f"API /api/reinstall 调用缺少hostname, system或password参数. Payload: {payload}")
            return jsonify({'code': 400, 'msg': '缺少hostname, system或password参数'}), 400
        logger.info(f"API请求reinstall for: {hostname} with OS: {new_os}")
        return jsonify(lxc.reinstall_container(hostname, new_os, new_password))
    except Exception as e:
        logger.error(f"处理 /api/reinstall 时发生意外错误: {e}", exc_info=True)
        return jsonify({'code': 500, 'msg': f'服务器内部错误: {e}'}), 500


@app.route('/api/natlist', methods=['GET'])
@api_key_required
def api_natlist():
    hostname = request.args.get('hostname')
    if not hostname:
        logger.warning("API /api/natlist 调用缺少 hostname 参数")
        return jsonify({'code': 400, 'msg': '缺少hostname参数'}), 400
    logger.info(f"API请求natlist for: {hostname}")
    return jsonify(lxc.list_nat_rules(hostname))

@app.route('/api/addport', methods=['POST'])
@api_key_required
def api_addport():
    hostname_from_form = request.form.get('hostname')
    hostname_from_query = request.args.get('hostname')
    hostname = hostname_from_form or hostname_from_query

    dtype = request.form.get('dtype')
    dport = request.form.get('dport')
    sport = request.form.get('sport')

    if not all([hostname, dtype, dport, sport]):
        logger.warning(f"API /api/addport 调用缺少参数. Hostname: {hostname}, dtype: {dtype}, dport: {dport}, sport: {sport}. Form: {request.form}, Args: {request.args}")
        return jsonify({'code': 400, 'msg': '缺少hostname, dtype, dport, 或 sport参数'}), 400
    logger.info(f"API请求addport for: {hostname}, {dtype}:{dport}->{sport}")
    return jsonify(lxc.add_nat_rule_via_iptables(hostname, dtype, dport, sport))

@app.route('/api/delport', methods=['POST'])
@api_key_required
def api_delport():
    hostname_from_form = request.form.get('hostname')
    hostname_from_query = request.args.get('hostname')
    hostname = hostname_from_form or hostname_from_query

    dtype = request.form.get('dtype')
    dport = request.form.get('dport')
    sport = request.form.get('sport')

    container_ip_at_creation = request.form.get('container_ip_at_creation', None)

    if not all([hostname, dtype, dport, sport]):
        logger.warning(f"API /api/delport 调用缺少参数. Hostname: {hostname}, dtype: {dtype}, dport: {dport}, sport: {sport}. Form: {request.form}, Args: {request.args}")
        return jsonify({'code': 400, 'msg': '缺少hostname, dtype, dport, 或 sport参数'}), 400
    logger.info(f"API请求delport for: {hostname}, {dtype}:{dport}->{sport}")
    return jsonify(lxc.delete_nat_rule_via_iptables(hostname, dtype, dport, sport, container_ip_at_creation_time=container_ip_at_creation))


if __name__ == '__main__':
    logger.info(f"启动LXD网页管理器，监听端口: {app_config.http_port}")
    logger.info("请使用您的TOKEN作为密码登录WebUI，或作为API Key用于外部模块调用。")
    app.run(host='0.0.0.0', port=app_config.http_port, debug=(app_config.log_level == 'DEBUG'))