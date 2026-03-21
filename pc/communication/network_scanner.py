import json
import socket
import time

from pc.core.config import get_config, set_config
from pc.core.logger import console_error, console_info, console_prompt


def _virtual_endpoints() -> list[str]:
    hosts_raw = str(get_config("network.virtual_pi_hosts", "") or "").strip()
    if hosts_raw:
        endpoints = [item.strip() for item in hosts_raw.split(",") if item.strip()]
        if endpoints:
            return endpoints
    host = str(get_config("network.virtual_pi_host", "127.0.0.1")).strip() or "127.0.0.1"
    return [host]


def scan_multi_nodes(expected_count: int, timeout: float = 3.0) -> dict:
    """Broadcast-discover Pi nodes, or return local virtual nodes when enabled."""
    console_info(f"正在扫描网络，预期寻找 {expected_count} 台设备...")

    if bool(get_config("network.virtual_pi_enabled", False)):
        endpoints = _virtual_endpoints()
        console_info(f"已启用本地虚拟 Pi 节点，直接使用 {len(endpoints)} 个端点: {endpoints}")
        return {str(i + 1): endpoint for i, endpoint in enumerate(endpoints)}

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.settimeout(timeout)

    msg = json.dumps({"type": "pc_discovery", "service": "video_analysis"}).encode("utf-8")
    found_ips = set()

    try:
        sock.sendto(msg, ("<broadcast>", 50000))
        start_time = time.time()
        while (time.time() - start_time) < timeout and len(found_ips) < expected_count:
            try:
                data, addr = sock.recvfrom(1024)
                payload = data.decode("utf-8", errors="ignore")
                resp = json.loads(payload)
                if resp.get("type") == "raspberry_pi_response":
                    ip = resp.get("ip", addr[0])
                    if ip not in found_ips:
                        found_ips.add(ip)
                        console_info(f"发现节点: {ip} ({len(found_ips)}/{expected_count})")
            except socket.timeout:
                break
            except Exception:
                continue
    finally:
        sock.close()

    return {str(i + 1): ip for i, ip in enumerate(sorted(found_ips))}


def get_lab_topology() -> dict:
    """Interactive discovery helper for multi-node monitoring."""
    while True:
        try:
            raw = input("\n[INFO] 请输入要连接的树莓派总数 (默认1): ").strip()
            expected = int(raw) if raw else 1
        except ValueError:
            continue

        pi_dict = scan_multi_nodes(expected)
        if len(pi_dict) < expected:
            console_error(f"仅发现 {len(pi_dict)} 台设备，低于预期的 {expected} 台。")
            console_prompt("1. 重新扫描")
            console_prompt("2. 按当前发现数量继续")
            console_prompt("3. 返回上级模式选择")
            choice = input("请选择 (1/2/3): ").strip()
            if choice == "1":
                continue
            if choice == "3":
                return {}
            if not pi_dict:
                continue

        set_config("network.multi_pis", json.dumps(pi_dict, ensure_ascii=False))
        console_info(f"拓扑已保存: {pi_dict}")
        return pi_dict
