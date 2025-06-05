<?php

use app\common\logic\RunMap;
use app\common\model\HostModel;
use think\Db;

function lxdserver_MetaData()
{
    return [
        'DisplayName' => '魔方财务-LXD对接插件 by xkatld & gemini',
        'APIVersion'  => '1.0.0',
        'HelpDoc'     => 'https://github.com/xkatld/zjmf-lxd-server',
    ];
}

function lxdserver_ConfigOptions()
{
    return [
        [
            'type'        => 'text',
            'name'        => '核心数',
            'description' => '核心',
            'default'     => '1',
            'key'         => 'CPU',
        ],
        [
            'type'        => 'text',
            'name'        => '硬盘大小',
            'description' => 'MB',
            'default'     => '1024',
            'key'         => 'Disk Space',
        ],
        [
            'type'        => 'text',
            'name'        => '内存',
            'description' => 'MB',
            'default'     => '128',
            'key'         => 'Memory',
        ],
        [
            'type'        => 'text',
            'name'        => '上行带宽',
            'description' => 'Mbps',
            'default'     => '1',
            'key'         => 'net_in',
        ],
        [
            'type'        => 'text',
            'name'        => '下行带宽',
            'description' => 'Mbps',
            'default'     => '1',
            'key'         => 'net_out',
        ],
        [
            'type'        => 'text',
            'name'        => '流量',
            'description' => 'GB(0为不限制)',
            'default'     => '2',
            'key'         => 'flow_limit',
        ],
        [
            'type'        => 'text',
            'name'        => '端口转发数',
            'description' => '条',
            'default'     => '2',
            'key'         => 'nat_acl_limit',
        ],
        [
            'type'        => 'text',
            'name'        => '默认镜像',
            'description' => '如果设置可选配置则优先可选配置',
            'key'         => 'os',
        ],
    ];
}

function lxdserver_TestLink($params)
{
    $data = [
        'url'  => '/api/check',
        'type' => 'application/x-www-form-urlencoded',
        'data' => [],
    ];

    $res = lxdserver_Curl($params, $data, 'GET');

    if ($res === null) {
        return [
            'status' => 200,
            'data'   => [
                'server_status' => 0,
                'msg'           => "无法连接到LXD API服务器，请检查服务器IP、端口或确认API服务是否正在运行。",
            ],
        ];
    } elseif (isset($res['code'])) {
        if ($res['code'] == 200 && isset($res['msg']) && $res['msg'] == 'API连接正常') {
            return [
                'status' => 200,
                'data'   => [
                    'server_status' => 1,
                    'msg'           => "LXD API服务器连接成功且API密钥有效。(" . $res['msg'] . ")",
                ],
            ];
        } elseif ($res['code'] == 401) {
            return [
                'status' => 200,
                'data'   => [
                    'server_status' => 0,
                    'msg'           => "LXD API服务器连接成功，但提供的API密钥无效。API响应: " . ($res['msg'] ?? '无详细错误信息'),
                ],
            ];
        } else {
            return [
                'status' => 200,
                'data'   => [
                    'server_status' => 0,
                    'msg'           => "LXD API服务器连接成功，但API响应了非预期的状态。API Code: " . $res['code'] . ", Msg: " . ($res['msg'] ?? 'N/A'),
                ],
            ];
        }
    } else {
        return [
            'status' => 200,
            'data'   => [
                'server_status' => 0,
                'msg'           => "连接到LXD API服务器但收到意外的响应格式 (缺少'code'字段)。响应: " . json_encode($res),
            ],
        ];
    }
}

function lxdserver_ClientArea($params)
{
    $panel = [
        'info'    => [
            'name' => '产品信息',
        ],
        'nat_acl' => [
            'name' => 'NAT转发',
        ],
    ];
    return $panel;
}

function lxdserver_ClientAreaOutput($params, $key)
{
    if ($key == 'info') {
        $data = [
            'url'  => '/api/getinfo?' . 'hostname=' . $params['domain'],
            'type' => 'application/x-www-form-urlencoded',
            'data' => [],
        ];
        $res = lxdserver_Curl($params, $data, 'GET');

        if (isset($res['code']) && $res['code'] == 200) {
            return [
                'template' => 'templates/info.html',
                'vars'     => [
                    'data' => $res['data'],
                ],
            ];
        }

        return [
            'template' => 'templates/error.html',
            'vars'     => [
                'msg' => $res['msg'] ?? '获取信息失败',
            ],
        ];
    } elseif ($key == 'nat_acl') {
        $data = [
            'url'  => '/api/natlist?' . 'hostname=' . $params['domain'],
            'type' => 'application/x-www-form-urlencoded',
            'data' => [],
        ];
        $res = lxdserver_Curl($params, $data, 'GET');
        return [
            'template' => 'templates/nat_acl.html',
            'vars'     => [
                'list' => $res['data'] ?? [],
                'msg'  => $res['msg'] ?? '',
            ],
        ];
    }
}

function lxdserver_AllowFunction()
{
    return [
        'client' => ['natadd', 'natdel'],
    ];
}

function lxdserver_CreateAccount($params)
{
    $sys_pwd = $params['password'] ?? randStr(8);

    $data = [
        'url'  => '/api/create',
        'type' => 'application/json',
        'data' => [
            'hostname'  => $params['domain'],
            'password'  => $sys_pwd,
            'cpu'       => $params['configoptions']['CPU'] ?? 1,
            'disk'      => $params["configoptions"]['Disk Space'] ?? 1024,
            'ram'       => $params["configoptions"]['Memory'] ?? 128,
            'system'    => $params["configoptions"]['os'] ?? '',
            'up'        => $params["configoptions"]['net_in'] ?? 1,
            'down'      => $params["configoptions"]['net_out'] ?? 1,
            'ports'     => (int)($params["configoptions"]['nat_acl_limit'] ?? 2),
            'bandwidth' => (int)($params["configoptions"]['flow_limit'] ?? 0),
        ],
    ];

    $res = lxdserver_JSONCurl($params, $data, 'POST');

    if (isset($res['code']) && $res['code'] == '200') {
        $update = [
            'dedicatedip'  => $params['server_ip'],
            'domainstatus' => 'Active',
            'username'     => $params['domain'],
            'password'     => $sys_pwd,
        ];
        Db::name('host')->where('id', $params['hostid'])->update($update);

        return ['status' => 'success', 'msg' => $res['msg'] ?? '创建成功'];
    } else {
        return ['status' => 'error', 'msg' => $res['msg'] ?? '创建失败'];
    }
}

function lxdserver_Sync($params)
{
    $data = [
        'url'  => '/api/getinfo?' . 'hostname=' . $params['domain'],
        'type' => 'application/x-www-form-urlencoded',
        'data' => [],
    ];
    $res = lxdserver_Curl($params, $data, 'GET');

    if (isset($res['code']) && $res['code'] == '200') {
        $update = [
            'dedicatedip' => $params['server_ip'],
        ];
        Db::name('host')->where('id', $params['hostid'])->update($update);

        return ['status' => 'success', 'msg' => $res['msg'] ?? '同步成功'];
    } else {
        return ['status' => 'error', 'msg' => $res['msg'] ?? '同步失败'];
    }
}

function lxdserver_TerminateAccount($params)
{
    $data = [
        'url'  => '/api/delete?' . 'hostname=' . $params['domain'],
        'type' => 'application/x-www-form-urlencoded',
        'data' => [],
    ];
    $res = lxdserver_Curl($params, $data, 'GET');

    if (isset($res['code']) && $res['code'] == '200') {
        return ['status' => 'success', 'msg' => $res['msg'] ?? '终止成功'];
    } else {
        return ['status' => 'error', 'msg' => $res['msg'] ?? '终止失败'];
    }
}

function lxdserver_On($params)
{
    $data = [
        'url'  => '/api/boot?' . 'hostname=' . $params['domain'],
        'type' => 'application/x-www-form-urlencoded',
        'data' => [],
    ];
    $res = lxdserver_Curl($params, $data, 'GET');

    if (isset($res['code']) && $res['code'] == '200') {
        return ['status' => 'success', 'msg' => $res['msg'] ?? '开机成功'];
    } else {
        return ['status' => 'error', 'msg' => $res['msg'] ?? '开机失败'];
    }
}

function lxdserver_Off($params)
{
    $data = [
        'url'  => '/api/stop?' . 'hostname=' . $params['domain'],
        'type' => 'application/x-www-form-urlencoded',
        'data' => [],
    ];
    $res = lxdserver_Curl($params, $data, 'GET');

    if (isset($res['code']) && $res['code'] == '200') {
        return ['status' => 'success', 'msg' => $res['msg'] ?? '关机成功'];
    } else {
        return ['status' => 'error', 'msg' => $res['msg'] ?? '关机失败'];
    }
}

function lxdserver_Reboot($params)
{
    $data = [
        'url'  => '/api/reboot?' . 'hostname=' . $params['domain'],
        'type' => 'application/x-www-form-urlencoded',
        'data' => [],
    ];
    $res = lxdserver_Curl($params, $data, 'GET');

    if (isset($res['code']) && $res['code'] == '200') {
        return ['status' => 'success', 'msg' => $res['msg'] ?? '重启成功'];
    } else {
        return ['status' => 'error', 'msg' => $res['msg'] ?? '重启失败'];
    }
}

function lxdserver_natadd($params)
{
    parse_str(file_get_contents("php://input"), $post);

    $dport = intval($post['dport'] ?? 0);
    $sport = intval($post['sport'] ?? 0);
    $dtype = strtolower(trim($post['dtype'] ?? ''));

    if (!($dtype == "tcp" || $dtype == "udp")) {
        return ['status' => 'error', 'msg' => '未知映射类型'];
    }
    if ($sport <= 0 || $sport > 65535) {
        return ['status' => 'error', 'msg' => '容器内部端口超过范围'];
    }
    if ($dport < 10000 || $dport > 65535) {
        return ['status' => 'error', 'msg' => '外网端口映射范围为10000-65535'];
    }

    $data = [
        'url'  => '/api/addport',
        'type' => 'application/x-www-form-urlencoded',
        'data' => 'hostname=' . urlencode($params['domain']) . '&dtype=' . urlencode($dtype) . '&dport=' . $dport . '&sport=' . $sport,
    ];

    $res = lxdserver_Curl($params, $data, 'POST');

    if (isset($res['code']) && $res['code'] == 200) {
        return ['status' => 'success', 'msg' => $res['msg'] ?? 'NAT转发添加成功'];
    } else {
        return ['status' => 'error', 'msg' => $res['msg'] ?? 'NAT转发添加失败'];
    }
}

function lxdserver_natdel($params)
{
    parse_str(file_get_contents("php://input"), $post);

    $dport = intval($post['dport'] ?? 0);
    $sport = intval($post['sport'] ?? 0);
    $dtype = strtolower(trim($post['dtype'] ?? ''));

    if (!($dtype == "tcp" || $dtype == "udp")) {
        return ['status' => 'error', 'msg' => '未知映射类型'];
    }
    if ($sport <= 0 || $sport > 65535) {
        return ['status' => 'error', 'msg' => '容器内部端口超过范围'];
    }
    if ($dport < 10000 || $dport > 65535) {
        return ['status' => 'error', 'msg' => '外网端口映射范围为10000-65535'];
    }

    $data = [
        'url'  => '/api/delport',
        'type' => 'application/x-www-form-urlencoded',
        'data' => 'hostname=' . urlencode($params['domain']) . '&dtype=' . urlencode($dtype) . '&dport=' . $dport . '&sport=' . $sport,
    ];

    $res = lxdserver_Curl($params, $data, 'POST');

    if (isset($res['code']) && $res['code'] == 200) {
        return ['status' => 'success', 'msg' => $res['msg'] ?? 'NAT转发删除成功'];
    } else {
        return ['status' => 'error', 'msg' => $res['msg'] ?? 'NAT转发删除失败'];
    }
}

function lxdserver_Status($params)
{
    $data = [
        'url'  => '/api/getinfo?' . 'hostname=' . $params['domain'],
        'type' => 'application/x-www-form-urlencoded',
        'data' => [],
    ];
    $res = lxdserver_Curl($params, $data, 'GET');

    if (isset($res['code']) && $res['code'] == 200) {
        $result = ['status' => 'success'];
        if (($res['data']['Status'] ?? '') == 'stop') {
            $result['data']['status'] = 'off';
            $result['data']['des']    = '关机';
        } elseif (($res['data']['Status'] ?? '') == 'running') {
            $result['data']['status'] = 'on';
            $result['data']['des']    = '运行中';
        } else {
            $result['data']['status'] = 'unknown';
            $result['data']['des']    = '未知';
        }
        return $result;
    } else {
        return ['status' => 'error', 'msg' => $res['msg'] ?? '获取状态失败'];
    }
}

function lxdserver_CrackPassword($params, $new_pass)
{
    $data = [
        'url'  => '/api/password',
        'type' => 'application/json',
        'data' => [
            'hostname' => $params['domain'],
            'password' => $new_pass,
        ],
    ];
    $res = lxdserver_JSONCurl($params, $data, 'POST');

    if (isset($res['code']) && $res['code'] == 200) {
        return ['status' => 'success', 'msg' => $res['msg'] ?? $res['message'] ?? '密码重置成功'];
    } else {
        return ['status' => 'error', 'msg' => $res['msg'] ?? $res['message'] ?? '密码重置失败'];
    }
}

function lxdserver_Reinstall($params)
{
    if (empty($params['reinstall_os'])) {
        return ['status' => 'error', 'msg' => '操作系统参数错误'];
    }

    $data = [
        'url'  => '/api/reinstall',
        'type' => 'application/json',
        'data' => [
            'hostname' => $params['domain'],
            'system'   => $params['reinstall_os'],
        ],
    ];
    $res = lxdserver_JSONCurl($params, $data, 'POST');

    if (isset($res['code']) && $res['code'] == 200) {
        return ['status' => 'success', 'msg' => $res['msg'] ?? $res['message'] ?? '重装成功'];
    } else {
        return ['status' => 'error', 'msg' => $res['msg'] ?? $res['message'] ?? '重装失败'];
    }
}

function lxdserver_JSONCurl($params, $data = [], $request = 'POST')
{
    $curl = curl_init();

    $url = 'http://' . $params['server_ip'] . ':' . $params['port'] . $data['url'];

    curl_setopt_array($curl, [
        CURLOPT_URL            => $url,
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_ENCODING       => '',
        CURLOPT_MAXREDIRS      => 10,
        CURLOPT_TIMEOUT        => 30,
        CURLOPT_CONNECTTIMEOUT => 10,
        CURLOPT_FOLLOWLOCATION => true,
        CURLOPT_HTTP_VERSION   => CURL_HTTP_VERSION_1_1,
        CURLOPT_CUSTOMREQUEST  => $request,
        CURLOPT_POSTFIELDS     => json_encode($data['data']),
        CURLOPT_HTTPHEADER     => [
            'apikey: ' . $params['accesshash'],
            'Content-Type: application/json',
        ],
    ]);

    $response = curl_exec($curl);
    $errno    = curl_errno($curl);

    curl_close($curl);

    if ($errno) {
        return null;
    }

    return json_decode($response, true);
}

function lxdserver_Curl($params, $data = [], $request = 'POST')
{
    $curl = curl_init();

    $url = 'http://' . $params['server_ip'] . ':' . $params['port'] . $data['url'];

    $postFields = ($request === 'POST' || $request === 'PUT') ? ($data['data'] ?? null) : null;
    if ($request === 'GET' && !empty($data['data']) && is_array($data['data'])) {
        $url .= (strpos($url, '?') === false ? '?' : '&') . http_build_query($data['data']);
    } elseif ($request === 'GET' && !empty($data['data']) && is_string($data['data'])) {
         $url .= (strpos($url, '?') === false ? '?' : '&') . $data['data'];
    }

    curl_setopt_array($curl, [
        CURLOPT_URL            => $url,
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_ENCODING       => '',
        CURLOPT_MAXREDIRS      => 10,
        CURLOPT_TIMEOUT        => 30,
        CURLOPT_CONNECTTIMEOUT => 10,
        CURLOPT_FOLLOWLOCATION => true,
        CURLOPT_HTTP_VERSION   => CURL_HTTP_VERSION_1_1,
        CURLOPT_CUSTOMREQUEST  => $request,
        CURLOPT_HTTPHEADER     => [
            'apikey: ' . $params['accesshash'],
            'Content-Type: ' . ($data['type'] ?? 'application/x-www-form-urlencoded'),
        ],
    ]);

    if ($postFields !== null) {
        curl_setopt($curl, CURLOPT_POSTFIELDS, $postFields);
    }

    $response = curl_exec($curl);
    $errno    = curl_errno($curl);

    curl_close($curl);

    if ($errno) {
        return null;
    }

    return json_decode($response, true);
}