<?php

use app\common\logic\RunMap;
use app\common\model\HostModel;
use think\Db;

function senkinlxc_MetaData(){
	return ['DisplayName'=>'Senkin的LXC对接插件', 'APIVersion'=>'1.0.0', 'HelpDoc'=>''];
}

function senkinlxc_ConfigOptions(){
	return [
		[
			'type'=>'text',
			'name'=>'核心数',
			'description'=>'核心',
			'default'=>'1',
			'key'=>'CPU',
		],
		[
			'type'=>'text',
			'name'=>'硬盘大小',
			'description'=>'MB',
			'default'=>'1024',
			'key'=>'Disk Space',
		],
        [
			'type'=>'text',
			'name'=>'内存',
			'description'=>'MB',
			'default'=>'128',
			'key'=>'Memory',
		],
        [
			'type'=>'text',
			'name'=>'上行带宽',
			'description'=>'Mbps',
			'default'=>'1',
			'key'=>'net_in',
		],
        [
			'type'=>'text',
			'name'=>'下行带宽',
			'description'=>'Mbps',
			'default'=>'1',
			'key'=>'net_out',
		],
		[
			'type'=>'text',
			'name'=>'流量',
			'description'=>'GB(0为不限制)',
			'default'=>'2',
			'key'=>'flow_limit',
		],
        [
			'type'=>'text',
			'name'=>'端口转发数',
			'description'=>'条',
			'default'=>'2',
			'key'=>'nat_acl_limit',
		],
        [
			'type'=>'text',
			'name'=>'默认镜像',
			'description'=>'如果设置可选配置则优先可选配置',
			'key'=>'os',
		],
	];
}



function senkinlxc_ClientArea($params){
    $panel = [
        'info'=>[
            'name'=>'产品信息',
            ],
        'nat_acl'=>[
            'name'=>'NAT转发',
            ]
		];
	return $panel;
}

function senkinlxc_ClientAreaOutput($params, $key){

	if($key == 'info'){
		$data = [
			'url' => '/api/getinfo?'.'hostname='.$params['domain'],
			'type' => 'application/x-www-form-urlencoded',
			'data' => []
		];
		$res = senkinlxc_Curl($params, $data, 'GET');
		if (isset($res['code']) && $res['code'] == 200) {
			return [
				'template'=>'templates/info.html',
				'vars'=>[
				   'data'=>$res['data']
				]
			];
		}
		return [
			'template'=>'templates/error.html',
		];
	}elseif ($key == 'nat_acl') {
		$data = [
			'url' => '/api/natlist?'.'hostname='.$params['domain'],
			'type' => 'application/x-www-form-urlencoded',
			'data' => []
		];
		$res = senkinlxc_Curl($params, $data, 'GET');
		return [
			'template'=>'templates/nat_acl.html',
			'vars'=>[
			    'list'=>$res['data'],
			]
		];
	}
}

function senkinlxc_AllowFunction(){
	return [
		'client'=>['natadd','natdel'],
	];
}

function senkinlxc_CreateAccount($params){
    if(empty($params['password'])){
		$sys_pwd = randStr(8);
	}else{
		$sys_pwd = $params['password'];
	}
    $data = [
        'url' => '/api/create',
        'type' => 'application/json',
        'data' => [
            'hostname' => $params['domain'],
            'password' => $sys_pwd,
            'cpu' => $params['configoptions']['CPU'],
            'disk' => $params["configoptions"]['Disk Space'],
            'ram' => $params["configoptions"]['Memory'],
            'system' => $params["configoptions"]['os'],
            'up' => $params["configoptions"]['net_in'],
            'down' => $params["configoptions"]['net_out'],
            'ports' => (int)$params["configoptions"]['nat_acl_limit'],
			'bandwidth' =>(int)$params["configoptions"]['flow_limit']
        ]
    ];
    $res = senkinlxc_JSONCurl($params, $data, 'POST');
    if($res['code'] == '200'){
        $update['dedicatedip'] = $params['server_ip'];
		$update['domainstatus'] = 'Active';
		$update['username'] = $params['domain'];
		$update['password'] = $sys_pwd;
		Db::name('host')->where('id', $params['hostid'])->update($update);
        return ['status'=>'success', 'msg'=>$res['msg']];
	}else{
		return ['status'=>'error', 'msg'=>$res['msg']];
	}
}

function senkinlxc_Sync($params){
	$data = [
        'url' => '/api/getinfo?'.'hostname='.$params['domain'],
        'type' => 'application/x-www-form-urlencoded',
        'data' => []
    ];
    $res = senkinlxc_Curl($params, $data, 'GET');
	if($res['code'] == '200'){
	    $update['dedicatedip'] = $params['server_ip'];
		$update['password'] = $params["configoptions"]["pass"];
	    Db::name('host')->where('id', $params['hostid'])->update($update);
		return ['status'=>'success', 'msg'=>$res['msg']];
	}else{
		return ['status'=>'error', 'msg'=>$res['msg']];
	}
}

function senkinlxc_TerminateAccount($params){
    $data = [
        'url' => '/api/delete?'.'hostname='.$params['domain'],
        'type' => 'application/x-www-form-urlencoded',
        'data' => []
    ];
    $res = senkinlxc_Curl($params, $data, 'GET');
	if($res['code'] == '200'){
		return ['status'=>'success', 'msg'=>$res['msg']];
	}else{
		return ['status'=>'error', 'msg'=>$res['msg']];
	}
}

function senkinlxc_On($params){
    $data = [
        'url' => '/api/boot?'.'hostname='.$params['domain'],
        'type' => 'application/x-www-form-urlencoded',
        'data' => []
    ];
    $res = senkinlxc_Curl($params, $data, 'GET');
	if($res['code'] == '200'){
		return ['status'=>'success', 'msg'=>$res['msg']];
	}else{
		return ['status'=>'error', 'msg'=>$res['msg']];
	}
}

function senkinlxc_Off($params){
    $data = [
        'url' => '/api/stop?'.'hostname='.$params['domain'],
        'type' => 'application/x-www-form-urlencoded',
        'data' => []
    ];
    $res = senkinlxc_Curl($params, $data, 'GET');
	if($res['code'] == '200'){
		return ['status'=>'success', 'msg'=>$res['msg']];
	}else{
		return ['status'=>'error', 'msg'=>$res['msg']];
	}
}

function senkinlxc_Reboot($params){
    $data = [
        'url' => '/api/reboot?'.'hostname='.$params['domain'],
        'type' => 'application/x-www-form-urlencoded',
        'data' => []
    ];
    $res = senkinlxc_Curl($params, $data, 'GET');
	if($res['code'] == '200'){
		return ['status'=>'success', 'msg'=>$res['msg']];
	}else{
		return ['status'=>'error', 'msg'=>$res['msg']];
	}
}

function senkinlxc_natadd($params){
	parse_str(file_get_contents("php://input"),$post);
	$dport = intval($post['dport']);
    $sport = intval($post['sport']);
    $dtype = trim($post['dtype']);
	if(!($dtype == "tcp" || $dtype == "udp")){$result = ['status'=>'error', 'msg'=>'未知映射类型'];return $result;}
	if($sport <= 0 || $sport > 65535){$result = ['status'=>'error', 'msg'=>'超过端口范围'];return $result;}
	if($dport <= 10000 || $dport > 65535){$result = ['status'=>'error', 'msg'=>'外网端口映射范围为10000-65535'];return $result;}
    $data = [
        'url' => '/api/addport',
        'type' => 'application/x-www-form-urlencoded',
        'data' => 'hostname='.$params['domain'].'&dtype='.$dtype.'&dport='.$dport.'&sport='.$sport
    ];
    $res = senkinlxc_Curl($params, $data, 'POST');
	if(isset($res['code']) && $res['code'] == 200){
		$result = ['status'=>'success', 'msg'=>$res['msg']];
	}else{
		$result = ['status'=>'error', 'msg'=>$res['msg'] ?: 'NAT转发添失败'];
	}
    return $result;
}

function senkinlxc_natdel($params){
	parse_str(file_get_contents("php://input"),$post);
	$dport = intval($post['dport']);
	$sport = intval($post['sport']);
	$dtype = strtolower(trim($post['dtype']));
	if(!($dtype == "tcp" || $dtype == "udp")){$result = ['status'=>'error', 'msg'=>'未知映射类型'];return $result;}
	if($sport <= 0 || $sport > 65535){$result = ['status'=>'error', 'msg'=>'超过端口范围'];return $result;}
	if($dport <= 10000 || $dport > 65535){$result = ['status'=>'error', 'msg'=>'外网端口映射范围为10000-65535'];return $result;}
    $data = [
        'url' => '/api/delport',
        'type' => 'application/x-www-form-urlencoded',
        'data' => 'hostname='.$params['domain'].'&dtype='.$dtype.'&dport='.$dport.'&sport='.$sport
    ];
    $res = senkinlxc_Curl($params, $data, 'POST');
	if(isset($res['code']) && $res['code'] == 200){
		$result = ['status'=>'success', 'msg'=>$res['msg']];
	}else{
		$result = ['status'=>'error', 'msg'=>$res['msg'] ?: 'NAT转发删除失败'];
	}
    return $result;
}

function senkinlxc_Status($params){
    $data = [
        'url' => '/api/getinfo?'.'hostname='.$params['domain'],
        'type' => 'application/x-www-form-urlencoded',
        'data' => []
    ];
    $res = senkinlxc_Curl($params, $data, 'GET');
    if (isset($res['code']) && $res['code'] == 200) {
		$result['status'] = 'success';
		if($res['data']['Status'] == 'stop'){
			$result['data']['status'] = 'off';
			$result['data']['des'] = '关机';
		}else if($res['data']['Status'] == 'running'){
			$result['data']['status'] = 'on';
			$result['data']['des'] = '运行中';
		}else{
			$result['data']['status'] = 'unknown';
            $result['data']['des'] = '未知';
		}
		return $result;
    }else{
		return ['status'=>'error', 'msg'=>$res['msg'] ?: '获取失败'];
	}
}

function senkinlxc_CrackPassword($params, $new_pass){
	$data = [
        'url' => '/api/password',
        'type' => 'application/json',
        'data' => [
            'hostname' => $params['domain'],
            'password' => $new_pass,
        ]
    ];
    $res = senkinlxc_JSONCurl($params, $data, 'POST');
	if(isset($res['code']) && $res['code'] == 200){
		return ['status'=>'success', 'msg'=>$res['message']];
	}else{
		return ['status'=>'error', 'msg'=>$res['message'] ?: '破解失败'];
	}
}

function senkinlxc_Reinstall($params){
	if(empty($params['reinstall_os'])){
		return '操作系统错误';
	}
	$data = [
        'url' => '/api/reinstall',
        'type' => 'application/json',
        'data' => [
            'hostname' => $params['domain'],
            'system' => $params['reinstall_os'],
        ]
    ];
    $res = senkinlxc_JSONCurl($params, $data, 'POST');
	if(isset($res['code']) && $res['code'] == 200){
		return ['status'=>'success', 'msg'=>$res['message']];
	}else{
		return ['status'=>'error', 'msg'=>$res['message'] ?: '重装失败'];
	}
}

function senkinlxc_JSONCurl($params, $data = [], $request = 'POST'){
$curl = curl_init();
curl_setopt_array($curl, array(
   CURLOPT_URL => 'http://'.$params['server_ip'].':'.$params['port'].$data['url'],
   CURLOPT_RETURNTRANSFER => true,
   CURLOPT_ENCODING => '',
   CURLOPT_MAXREDIRS => 10,
   CURLOPT_TIMEOUT => 0,
   CURLOPT_FOLLOWLOCATION => true,
   CURLOPT_HTTP_VERSION => CURL_HTTP_VERSION_1_1,
   CURLOPT_CUSTOMREQUEST => $request,
   CURLOPT_POSTFIELDS => json_encode($data['data']),
   CURLOPT_HTTPHEADER => array(
      'apikey: '.$params['accesshash'],
      'Content-Type: '.$data['type']
   ),
));
$response = curl_exec($curl);
curl_close($curl);
return json_decode($response,true);
}

function senkinlxc_Curl($params, $data = [], $request = 'POST'){
$curl = curl_init();
curl_setopt_array($curl, array(
   CURLOPT_URL => 'http://'.$params['server_ip'].':'.$params['port'].$data['url'],
   CURLOPT_RETURNTRANSFER => true,
   CURLOPT_ENCODING => '',
   CURLOPT_MAXREDIRS => 10,
   CURLOPT_TIMEOUT => 0,
   CURLOPT_FOLLOWLOCATION => true,
   CURLOPT_HTTP_VERSION => CURL_HTTP_VERSION_1_1,
   CURLOPT_CUSTOMREQUEST => $request,
   CURLOPT_POSTFIELDS => $data['data'],
   CURLOPT_HTTPHEADER => array(
      'apikey: '.$params['accesshash'],
      'Content-Type: '.$data['type']
   ),
));
$response = curl_exec($curl);
curl_close($curl);
return json_decode($response,true);
}