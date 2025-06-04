from flask import Flask, request, jsonify
from functools import wraps
import logging
from config_handler import app_config
from lxc_manager import LXCManager

app = Flask(__name__)
lxc_manager = LXCManager()

logging.basicConfig(level=getattr(logging, app_config.log_level, logging.INFO),
                    format='%(asctime)s %(levelname)s: %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S')

def api_key_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if request.headers.get('apikey') == app_config.token:
            return f(*args, **kwargs)
        logging.warning(f"认证失败: 无效的API Key from {request.remote_addr}")
        return jsonify({'code': 401, 'msg': '认证失败或API密钥无效'}), 401
    return decorated_function

@app.route('/api/getinfo', methods=['GET'])
@api_key_required
def api_getinfo():
    hostname = request.args.get('hostname')
    if not hostname: return jsonify({'code': 400, 'msg': '缺少hostname参数'}), 400
    logging.info(f"请求getinfo: {hostname}")
    return jsonify(lxc_manager.get_container_info(hostname))

@app.route('/api/create', methods=['POST'])
@api_key_required
def api_create():
    payload = request.json
    if not payload or not payload.get('hostname'):
        return jsonify({'code': 400, 'msg': '无效的请求体或缺少hostname'}), 400
    logging.info(f"请求create: {payload.get('hostname')}")
    return jsonify(lxc_manager.create_container(payload))

@app.route('/api/delete', methods=['GET'])
@api_key_required
def api_delete():
    hostname = request.args.get('hostname')
    if not hostname: return jsonify({'code': 400, 'msg': '缺少hostname参数'}), 400
    logging.info(f"请求delete: {hostname}")
    return jsonify(lxc_manager.delete_container(hostname))

@app.route('/api/boot', methods=['GET'])
@api_key_required
def api_boot():
    hostname = request.args.get('hostname')
    if not hostname: return jsonify({'code': 400, 'msg': '缺少hostname参数'}), 400
    logging.info(f"请求boot: {hostname}")
    return jsonify(lxc_manager.start_container(hostname))

@app.route('/api/stop', methods=['GET'])
@api_key_required
def api_stop():
    hostname = request.args.get('hostname')
    if not hostname: return jsonify({'code': 400, 'msg': '缺少hostname参数'}), 400
    logging.info(f"请求stop: {hostname}")
    return jsonify(lxc_manager.stop_container(hostname))

@app.route('/api/reboot', methods=['GET'])
@api_key_required
def api_reboot():
    hostname = request.args.get('hostname')
    if not hostname: return jsonify({'code': 400, 'msg': '缺少hostname参数'}), 400
    logging.info(f"请求reboot: {hostname}")
    return jsonify(lxc_manager.restart_container(hostname))

@app.route('/api/password', methods=['POST'])
@api_key_required
def api_password():
    payload = request.json
    hostname = payload.get('hostname')
    new_pass = payload.get('password')
    if not hostname or not new_pass:
        return jsonify({'code': 400, 'msg': '缺少hostname或password参数'}), 400
    logging.info(f"请求password change for: {hostname}")
    return jsonify(lxc_manager.change_password(hostname, new_pass))

@app.route('/api/reinstall', methods=['POST'])
@api_key_required
def api_reinstall():
    payload = request.json
    hostname = payload.get('hostname')
    new_os = payload.get('system')
    if not hostname or not new_os:
        return jsonify({'code': 400, 'msg': '缺少hostname或system参数'}), 400
    logging.info(f"请求reinstall for: {hostname} with OS: {new_os}")
    return jsonify(lxc_manager.reinstall_container(hostname, new_os))

@app.route('/api/natlist', methods=['GET'])
@api_key_required
def api_natlist():
    hostname = request.args.get('hostname')
    if not hostname: return jsonify({'code': 400, 'msg': '缺少hostname参数'}), 400
    logging.info(f"请求natlist for: {hostname}")
    return jsonify(lxc_manager.list_nat_rules(hostname))

@app.route('/api/addport', methods=['POST'])
@api_key_required
def api_addport():
    hostname = request.form.get('hostname')
    if not hostname: hostname = request.args.get('hostname')
    
    dtype = request.form.get('dtype')
    dport = request.form.get('dport')
    sport = request.form.get('sport')

    if not all([hostname, dtype, dport, sport]):
        return jsonify({'code': 400, 'msg': '缺少hostname, dtype, dport, 或 sport参数'}), 400
    logging.info(f"请求addport for: {hostname}, {dtype}:{dport}->{sport}")
    return jsonify(lxc_manager.add_nat_rule(hostname, dtype, dport, sport))

@app.route('/api/delport', methods=['POST'])
@api_key_required
def api_delport():
    hostname = request.form.get('hostname')
    if not hostname: hostname = request.args.get('hostname')

    dtype = request.form.get('dtype')
    dport = request.form.get('dport')
    sport = request.form.get('sport')

    if not all([hostname, dtype, dport, sport]):
        return jsonify({'code': 400, 'msg': '缺少hostname, dtype, dport, 或 sport参数'}), 400
    logging.info(f"请求delport for: {hostname}, {dtype}:{dport}->{sport}")
    return jsonify(lxc_manager.delete_nat_rule(hostname, dtype, dport, sport))

@app.route('/api/domainlist', methods=['GET'])
@api_key_required
def api_domainlist():
    hostname = request.args.get('hostname')
    if not hostname: return jsonify({'code': 400, 'msg': '缺少hostname参数'}), 400
    logging.info(f"请求domainlist for: {hostname}")
    return jsonify(lxc_manager.list_domain_bindings(hostname))

@app.route('/api/adddomain', methods=['POST'])
@api_key_required
def api_adddomain():
    hostname = request.form.get('hostname')
    if not hostname: hostname = request.args.get('hostname')
    domain = request.form.get('domain')
    if not all([hostname, domain]):
        return jsonify({'code': 400, 'msg': '缺少hostname或domain参数'}), 400
    logging.info(f"请求adddomain for: {hostname}, domain: {domain}")
    return jsonify(lxc_manager.add_domain_binding(hostname, domain))

@app.route('/api/deldomain', methods=['POST'])
@api_key_required
def api_deldomain():
    hostname = request.form.get('hostname')
    if not hostname: hostname = request.args.get('hostname')
    domain = request.form.get('domain')
    if not all([hostname, domain]):
        return jsonify({'code': 400, 'msg': '缺少hostname或domain参数'}), 400
    logging.info(f"请求deldomain for: {hostname}, domain: {domain}")
    return jsonify(lxc_manager.delete_domain_binding(hostname, domain))

if __name__ == '__main__':
    try:
        app.run(host='0.0.0.0', port=app_config.http_port, debug=(app_config.log_level == 'DEBUG'))
    except RuntimeError as e:
        logging.critical(f"应用启动失败: {e}")
    except Exception as e:
        logging.critical(f"发生未捕获的异常导致应用启动失败: {e}")
