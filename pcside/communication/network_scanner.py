import socket
import json
import time
from pcside.core.config import set_config
from pcside.core.logger import console_info, console_error, console_prompt


def scan_multi_nodes(expected_count: int, timeout: float = 3.0) -> dict:
    """广播并发现局域网内的多台树莓派"""
    console_info(f"正在扫描网络，预期寻找 {expected_count} 台设备...")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.settimeout(timeout)

    msg = json.dumps({'type': 'pc_discovery', 'service': 'video_analysis'}).encode('utf-8')
    found_ips = set()

    try:
        sock.sendto(msg, ('<broadcast>', 50000))
        start_time = time.time()
        while (time.time() - start_time) < timeout and len(found_ips) < expected_count:
            try:
                data, addr = sock.recvfrom(1024)
                # ★ 核心修复：加上 errors='ignore'，无视局域网里其他设备的二进制脏数据
                payload = data.decode('utf-8', errors='ignore')
                resp = json.loads(payload)

                if resp.get('type') == 'raspberry_pi_response':
                    ip = resp.get('ip', addr[0])
                    if ip not in found_ips:
                        found_ips.add(ip)
                        console_info(f"发现节点: {ip} ({len(found_ips)}/{expected_count})")
            except socket.timeout:
                break
            except Exception:
                # 遇到非 JSON 格式的干扰包直接忽略，继续监听下一个
                continue
    finally:
        sock.close()

    return {str(i + 1): ip for i, ip in enumerate(sorted(list(found_ips)))}


def get_lab_topology() -> dict:
    """交互式确定实验室拓扑：处理设备不足或回退"""
    while True:
        try:
            val = input("\n[INFO] 请输入要连接的树莓派总数 (默认1): ").strip()
            expected = int(val) if val else 1
        except ValueError:
            continue

        pi_dict = scan_multi_nodes(expected)

        if len(pi_dict) < expected:
            console_error(f"⚠️ 仅发现 {len(pi_dict)} 台设备，未达到预期的 {expected} 台。")
            console_prompt("1. 重新扫描")
            console_prompt("2. 就按当前发现的数量继续 (自动重新编号)")
            console_prompt("3. 回退到上级模式选择")
            choice = input("请选择 (1/2/3): ").strip()

            if choice == '1': continue
            if choice == '3': return {}
            if not pi_dict: continue

        # 自动将编号后的 IP 字典存入配置 (序列化为JSON字符串)
        set_config("network.multi_pis", json.dumps(pi_dict))
        console_info(f"拓扑已保存: {pi_dict}")
        return pi_dict