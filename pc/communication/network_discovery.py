#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
network_discovery.py - 网络发现模块
用于自动发现PC和树莓派设备并建立连接
"""

import socket
import json
import time
import threading
import requests
from typing import Optional

# 尝试导入核心模块，处理可能的导入错误
try:
    # 尝试相对导入
    from .logger import console_info, console_error
except ImportError:
    try:
        # 尝试绝对导入
        from core.logger import console_info, console_error
    except ImportError:
        # 定义简单的替代函数
        def console_info(text: str):
            print(f"[INFO] {text}")


        def console_error(text: str):
            import time
            print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} [ERROR] {text}")


def get_local_ip() -> str:
    """
    获取本机IP地址
    Returns:
        str: 本机IP地址
    """
    try:
        # 创建一个UDP socket，不实际发送数据
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # 连接到一个公共DNS服务器（不会真正连接）
        s.connect(("8.8.8.8", 80))
        # 获取socket的IP地址
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        # 备用方法
        try:
            return socket.gethostbyname(socket.gethostname())
        except:
            return "127.0.0.1"


def get_network_prefix() -> str:
    """
    获取网络前缀，如'192.168.1.'
    Returns:
        str: 网络前缀
    """
    local_ip = get_local_ip()
    # 假设是C类网络，前三个部分是网络前缀
    return '.'.join(local_ip.split('.')[:3]) + '.'


def _is_port_open(ip: str, port: int) -> bool:
    """
    检查端口是否开放
    Args:
        ip: IP地址
        port: 端口号
    Returns:
        bool: 端口是否开放
    """
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.5)
        result = sock.connect_ex((ip, port))
        sock.close()
        return result == 0
    except Exception as e:
        console_error(f"端口检查异常: {str(e)}")
        return False


class NetworkDiscovery:
    """
    网络发现服务，用于PC和树莓派之间的自动发现和连接
    """

    def __init__(self, discovery_port=50000, service_name="video_analysis"):
        self.discovery_port = discovery_port
        self.service_name = service_name
        self.local_ip = get_local_ip()
        self.discovery_socket = None
        self.running = False
        self.discovered_devices = {}
        self.pi_ip = None
        self.on_pi_found = None

    def start(self):
        """启动发现服务"""
        if self.running:
            return

        self.running = True
        self.discovery_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.discovery_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self.discovery_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        try:
            self.discovery_socket.bind(("", self.discovery_port))
        except Exception as e:
            console_error(f"绑定发现端口失败: {e}")
            self.running = False
            return

        self.discovery_socket.settimeout(1)

        # 启动发现线程
        threading.Thread(target=self._discovery_loop, daemon=True).start()
        console_info(f"网络发现服务已启动 (端口: {self.discovery_port})")

    def stop(self):
        """停止发现服务"""
        self.running = False
        if self.discovery_socket:
            self.discovery_socket.close()
        console_info("网络发现服务已停止")

    def _discovery_loop(self):
        """发现循环"""
        while self.running:
            try:
                # 接收发现消息
                data, addr = self.discovery_socket.recvfrom(1024)
                message = data.decode('utf-8')

                try:
                    info = json.loads(message)
                    device_type = info.get('type')
                    service = info.get('service')

                    if service == self.service_name:
                        if device_type == 'pc_discovery':
                            # 响应PC的发现请求
                            self._respond_to_pc(addr)
                        elif device_type == 'raspberry_pi_response':
                            # 记录发现的设备
                            self._record_discovered_device(info, addr[0])
                except json.JSONDecodeError:
                    pass
            except socket.timeout:
                pass
            except Exception as e:
                console_error(f"发现服务异常: {e}")

    def _respond_to_pc(self, addr):
        """响应PC的发现请求"""
        response = json.dumps({
            'type': 'raspberry_pi_response',
            'ip': self.local_ip,
            'service': self.service_name
        })
        try:
            self.discovery_socket.sendto(response.encode('utf-8'), addr)
        except Exception as e:
            console_error(f"响应PC发现请求失败: {str(e)}")

    def _record_discovered_device(self, info, ip):
        """记录发现的设备"""
        device_type = info.get('type')
        if device_type == 'raspberry_pi_response':
            self.pi_ip = ip
            self.discovered_devices['raspberry_pi'] = ip
            console_info(f"发现树莓派: {ip}")
            if self.on_pi_found:
                self.on_pi_found(ip)

    def broadcast_presence(self):
        """广播本机存在"""
        if not self.running:
            return

        message = json.dumps({
            'type': 'pc_discovery',
            'ip': self.local_ip,
            'service': self.service_name
        })
        try:
            self.discovery_socket.sendto(message.encode('utf-8'), ('<broadcast>', self.discovery_port))
        except Exception as e:
            console_error(f"广播失败: {str(e)}")

    def find_raspberry_pi(self, timeout=15) -> Optional[str]:
        """查找树莓派"""
        console_info("正在搜索树莓派...")

        # 清空之前的发现
        self.pi_ip = None
        if 'raspberry_pi' in self.discovered_devices:
            del self.discovered_devices['raspberry_pi']

        # 广播PC存在
        self.broadcast_presence()

        # 等待响应
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self.pi_ip:
                return self.pi_ip
            time.sleep(0.5)

        # 如果还是没找到，尝试端口扫描
        network_prefix = get_network_prefix()
        for i in range(1, 255):
            ip = f"{network_prefix}{i}"
            if i != int(self.local_ip.split('.')[-1]):  # 跳过自己
                if _is_port_open(ip, 8001):  # WebSocket端口
                    console_info(f"在 {ip} 上发现开放端口 8001")
                    # 额外验证
                    try:
                        response = requests.get(f"http://{ip}:8001", timeout=1)
                        if "树莓派视频流服务器" in response.text:
                            self.pi_ip = ip
                            self.discovered_devices['raspberry_pi'] = ip
                            return ip
                    except requests.RequestException as e:
                        console_error(f"验证树莓派失败: {str(e)}")
                    except Exception as e:
                        console_error(f"验证过程中异常: {str(e)}")

        console_info("未发现树莓派")
        return None


# 单例实例
_discovery_service = None


def get_discovery_service() -> NetworkDiscovery:
    """
    获取网络发现服务单例
    Returns:
        NetworkDiscovery: 网络发现服务实例
    """
    global _discovery_service
    if _discovery_service is None:
        _discovery_service = NetworkDiscovery()
        _discovery_service.start()
    return _discovery_service