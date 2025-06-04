from flask import Flask, request, jsonify
from functools import wraps
import logging
from config_handler import app_config
from lxc_manager import LXCManager

app = Flask(__name__)
lxc_manager = LXCManager()

logging.basicConfig(level=getattr(logging, app_config.log_level, logging.INFO),
                    format='%(asctime)s %(levelname)s: %(message)s [%(filename)s:%(lineno)d]',
                    datefmt='%Y-%m-%d %H:%M:%S')

logger = logging.getLogger(__name__)

def api_key_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        provided_key = request.headers.get('apikey')
        if provided_key and provided_key == app_config.token:
            return f(*args, **kwargs)
        else:
            logger.warning(f"认证失败: 无效的API Key from {request.remote_addr}.提供的Key: '{provided_key}'")
            return jsonify({'code': 401, 'msg': '认证失败或API密钥无效'}), 401
    return decorated_function

@app.route('/api/getinfo', methods=['GET'])
@api_key_required
def api_getinfo():
    hostname = request.args.get('hostname')
    if not hostname:
        logger.warning("API /api/getinfo 调用缺少 hostname 参数")
        return jsonify({'code': 400, 'msg': '缺少hostname参数'}), 400
    logger.info(f"请求getinfo for: {hostname}")
    return jsonify(lxc_manager.get_container_info(hostname))

@app.route('/api/create', methods=['POST'])
@api_key_required
def api_create():
    try:
        payload = request.json
        if not payload or not payload.get('hostname'):
            logger.warning(f"API /api/create 调用请求体无效或缺少hostname. Payload: {payload}")
            return jsonify({'code': 400, 'msg': '无效的请求体或缺少hostname'}), 400
        logger.info(f"请求create for: {payload.get('hostname')}")
        return jsonify(lxc_manager.create_container(payload))
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
    logger.info(f"请求delete for: {hostname}")
    return jsonify(lxc_manager.delete_container(hostname))

@app.route('/api/boot', methods=['GET'])
@api_key_required
def api_boot():
    hostname = request.args.get('hostname')
    if not hostname:
        logger.warning("API /api/boot 调用缺少 hostname 参数")
        return jsonify({'code': 400, 'msg': '缺少hostname参数'}), 400
    logger.info(f"请求boot for: {hostname}")
    return jsonify(lxc_manager.start_container(hostname))

@app.route('/api/stop', methods=['GET'])
@api_key_required
def api_stop():
    hostname = request.args.get('hostname')
    if not hostname:
        logger.warning("API /api/stop 调用缺少 hostname 参数")
        return jsonify({'code': 400, 'msg': '缺少hostname参数'}), 400
    logger.info(f"请求stop for: {hostname}")
    return jsonify(lxc_manager.stop_container(hostname))

@app.route('/api/reboot', methods=['GET'])
@api_key_required
def api_reboot():
    hostname = request.args.get('hostname')
    if not hostname:
        logger.warning("API /api/reboot 调用缺少 hostname 参数")
        return jsonify({'code': 400, 'msg': '缺少hostname参数'}), 400
    logger.info(f"请求reboot for: {hostname}")
    return jsonify(lxc_manager.restart_container(hostname))

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
        logger.info(f"请求password change for: {hostname}")
        return jsonify(lxc_manager.change_password(hostname, new_pass))
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
        if not hostname or not new_os:
            logger.warning(f"API /api/reinstall 调用缺少hostname或system参数. Payload: {payload}")
            return jsonify({'code': 400, 'msg': '缺少hostname或system参数'}), 400
        logger.info(f"请求reinstall for: {hostname} with OS: {new_os}")
        return jsonify(lxc_manager.reinstall_container(hostname, new_os))
    except Exception as e:
        logger.error(f"处理 /api/reinstall 时发生意外错误: {e}", exc_info=True)
        return jsonify({'code': 500, 'msg': '服务器内部错误'}), 500


@app.route('/api/natlist', methods=['GET'])
@api_key_required
def api_natlist():
    hostname = request.args.get('hostname')
    if not hostname:
        logger.warning("API /api/natlist 调用缺少 hostname 参数")
        return jsonify({'code': 400, 'msg': '缺少hostname参数'}), 400
    logger.info(f"请求natlist for: {hostname}")
    return jsonify(lxc_manager.list_nat_rules(hostname))

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
    logger.info(f"请求addport for: {hostname}, {dtype}:{dport}->{sport}")
    return jsonify(lxc_manager.add_nat_rule_via_iptables(hostname, dtype, dport, sport))

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
    logger.info(f"请求delport for: {hostname}, {dtype}:{dport}->{sport}")
    return jsonify(lxc_manager.delete_nat_rule_via_iptables(hostname, dtype, dport, sport, container_ip_at_creation_time=container_ip_at_creation))


@app.route('/api/domainlist', methods=['GET'])
@api_key_required
def api_domainlist():
    hostname = request.args.get('hostname')
    if not hostname:
        logger.warning("API /api/domainlist 调用缺少 hostname 参数")
        return jsonify({'code': 400, 'msg': '缺少hostname参数'}), 400
    logger.info(f"请求domainlist for: {hostname}")
    return jsonify(lxc_manager.list_domain_bindings(hostname))

@app.route('/api/adddomain', methods=['POST'])
@api_key_required
def api_adddomain():
    hostname_from_form = request.form.get('hostname')
    hostname_from_query = request.args.get('hostname')
    hostname = hostname_from_form or hostname_from_query

    domain = request.form.get('domain')
    if not all([hostname, domain]):
        logger.warning(f"API /api/adddomain 调用缺少hostname或domain参数. Hostname: {hostname}, Domain: {domain}. Form: {request.form}, Args: {request.args}")
        return jsonify({'code': 400, 'msg': '缺少hostname或domain参数'}), 400
    logger.info(f"请求adddomain for: {hostname}, domain: {domain}")
    return jsonify(lxc_manager.add_domain_binding(hostname, domain))

@app.route('/api/deldomain', methods=['POST'])
@api_key_required
def api_deldomain():
    hostname_from_form = request.form.get('hostname')
    hostname_from_query = request.args.get('hostname')
    hostname = hostname_from_form or hostname_from_query

    domain = request.form.get('domain')
    if not all([hostname, domain]):
        logger.warning(f"API /api/deldomain 调用缺少hostname或domain参数. Hostname: {hostname}, Domain: {domain}. Form: {request.form}, Args: {request.args}")
        return jsonify({'code': 400, 'msg': '缺少hostname或domain参数'}), 400
    logger.info(f"请求deldomain for: {hostname}, domain: {domain}")
    return jsonify(lxc_manager.delete_domain_binding(hostname, domain))

if __name__ == '__main__':
    try:
        logger.info(f"应用开始启动，监听端口: {app_config.http_port}, 日志级别: {app_config.log_level}")
        app.run(host='0.0.0.0', port=app_config.http_port, debug=(app_config.log_level == 'DEBUG'))
    except RuntimeError as e:
        logger.critical(f"应用启动失败 (RuntimeError): {e}", exc_info=True)
    except Exception as e:
        logger.critical(f"发生未捕获的异常导致应用启动失败: {e}", exc_info=True)