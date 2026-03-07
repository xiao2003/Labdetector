#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# !/usr/bin/env python3
# -*- coding: utf-8 -*-
import asyncio
import websockets
import threading
import queue
import time
import os
import sys
import socket
import json
import requests
import subprocess
from typing import Optional, Callable

# 尝试多种导入方式
try:
    # 尝试相对导入（当作为包的一部分导入时）
    from ..core.network import get_local_ip, get_network_prefix
except ImportError:
    try:
        # 尝试绝对导入（当作为独立模块导入时）
        from core.network import get_local_ip, get_network_prefix
    except ImportError:
        try:
            # 尝试通过sys.path添加项目根目录
            current_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.abspath(os.path.join(current_dir, "..", ".."))
            if project_root not in sys.path:
                sys.path.insert(0, project_root)

            from core.network import get_local_ip, get_network_prefix
        except ImportError:
            # 定义简单的替代函数（回退实现）
            def get_local_ip() -> str:
                """模拟的get_local_ip函数"""
                return "127.0.0.1"


            def get_network_prefix() -> str:
                """模拟的get_network_prefix函数"""
                return "192.168.31."

# 尝试多种导入方式，确保在不同执行环境中都能工作
try:
    # 尝试相对导入（当作为包的一部分导入时）
    from ..core.logger import console_info, console_error, console_status
    from ..core.config import get_config, set_config
except ImportError:
    try:
        # 尝试绝对导入（当作为独立模块导入时）
        from core.logger import console_info, console_error, console_status
        from core.config import get_config, set_config
    except ImportError:
        try:
            # 尝试通过sys.path添加项目根目录
            current_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.abspath(os.path.join(current_dir, "..", ".."))
            if project_root not in sys.path:
                sys.path.insert(0, project_root)

            from core.logger import console_info, console_error, console_status
            from core.config import get_config, set_config
        except ImportError:
            # 定义简单的替代函数（回退实现）
            def console_info(text: str):
                print(f"[INFO] {text}")


            def console_error(text: str):
                import time
                print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} [ERROR] {text}")


            def console_status(text: str):
                print(text)


            def get_config(key_path: str, default=None):
                """模拟的get_config函数"""
                parts = key_path.split('.')
                if parts[0] == "websocket" and parts[1] == "host":
                    return "192.168.31.31"
                elif parts[0] == "websocket" and parts[1] == "port":
                    return 8001
                elif parts[0] == "ws_retry" and parts[1] == "max_attempts":
                    return 5
                elif parts[0] == "ws_retry" and parts[1] == "interval":
                    return 3
                return default


            def set_config(key_path: str, value):
                """模拟的set_config函数"""
                console_info(f"模拟设置配置: {key_path} = {value}")

# 全局配置
CONFIG = {
    "websocket": {
        "host": get_config("websocket.host", "192.168.31.31"),
        "port": get_config("websocket.port", 8001)
    },
    "ws_retry": {
        "max_attempts": get_config("ws_retry.max_attempts", 5),
        "interval": get_config("ws_retry.interval", 3)
    }
}

# 全局状态
_STATE = {
    "running": True,
    "connected": False,
    "ws_loop": None,
    "ws_task": None,
    "retry_attempts": 0
}


# ====================== 网络发现功能 ======================

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
        self.local_ip = get_local_ip()  # 使用新添加的函数
        self.discovery_socket = None
        self.running = False
        self.discovered_devices = {}
        self.pi_ip = None
        self.on_pi_found = None
        self.last_broadcast_time = 0
        self.broadcast_interval = 5  # 每5秒广播一次

    # ...其他方法保持不变...

    def find_raspberry_pi(self, timeout=15) -> Optional[str]:
        """查找树莓派"""
        console_info("正在搜索网络中的树莓派...")

        # 尝试从配置获取已知的树莓派IP
        known_pi_ip = get_config("network.pi_ip")
        if known_pi_ip and known_pi_ip != "192.168.31.31" and not known_pi_ip.startswith("127."):
            console_info(f"尝试连接已知树莓派地址: {known_pi_ip}")
            if _is_port_open(known_pi_ip, 8001):
                console_info(f"成功连接到树莓派: {known_pi_ip}")
                return known_pi_ip

        # 如果已知IP不可用，进行网络搜索
        try:
            # 获取本机IP和网络前缀 - 现在可以正确调用
            local_ip = get_local_ip()
            network_prefix = get_network_prefix()  # 现在可以正确调用

            console_info(f"扫描网络段: {network_prefix}x")

            # 扫描整个子网
            for i in range(1, 255):
                ip = f"{network_prefix}{i}"
                # 跳过本机IP和回环地址
                if ip == local_ip or ip.startswith("127."):
                    continue

                # 检查8001端口是否开放
                if _is_port_open(ip, 8001):
                    console_info(f"在 {ip} 上发现开放端口 8001")
                    # 额外验证 - 检查是否是我们的树莓派服务
                    try:
                        response = requests.get(f"http://{ip}:8001", timeout=2)
                        if "树莓派视频流服务器" in response.text or "WebSocket服务器" in response.text:
                            console_info(f"确认发现树莓派: {ip}")
                            # 保存到配置
                            set_config("network.pi_ip", ip)
                            return ip
                    except Exception:
                        continue

            console_info("未发现树莓派")
            return None
        except Exception as e:
            console_error(f"网络搜索异常: {str(e)}")
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


# ====================== 语音结果发送器 ======================

class VoiceResultSender:
    """语音识别结果发送器 - 专门用于向树莓派发送语音识别结果"""

    def __init__(self):
        self.host = get_config("websocket.host", "192.168.31.31")
        self.port = get_config("websocket.port", 8001)
        self.uri = f"ws://{self.host}:{self.port}"
        self._q: queue.Queue = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self.connected = False
        self._stop_event = threading.Event()
        self._callback: Optional[Callable[[str], None]] = None
        self.discovery_service = get_discovery_service()

        # 设置发现回调
        self.discovery_service.on_pi_found = self._on_pi_found

    def _on_pi_found(self, pi_ip: str):
        """当发现树莓派时的回调"""
        console_info(f"自动发现树莓派: {pi_ip}")
        # 更新WebSocket配置
        set_config("websocket.host", pi_ip)
        # 更新URI
        self.uri = f"ws://{pi_ip}:{self.port}"
        # 尝试重新连接
        self.start()

    def start(self, callback: Optional[Callable[[str], None]] = None):
        """启动发送服务"""
        if self._thread and self._thread.is_alive():
            return

        self._callback = callback
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """停止发送服务"""
        try:
            self._stop_event.set()
            self._q.put_nowait(None)
        except Exception:
            pass
        if self._thread:
            self._thread.join(timeout=2.0)

    def send(self, text: str, priority: int = 0) -> bool:
        """
        发送语音识别结果到树莓派
        Args:
            text: 要发送的文本内容
            priority: 优先级（0:普通，1:高优先级）
        Returns:
            bool: 是否成功入队
        """
        try:
            # 高优先级消息插入队列头部
            if priority == 1:
                # 使用临时队列实现优先级插入
                temp_queue = queue.Queue()
                while not self._q.empty():
                    temp_queue.put(self._q.get())
                self._q.put(text)
                while not temp_queue.empty():
                    self._q.put(temp_queue.get())
            else:
                self._q.put_nowait(text)
            return True
        except queue.Full:
            console_error("消息队列已满")
            return False
        except Exception as e:
            console_error(f"消息入队失败: {e}")
            return False

    def _run_loop(self):
        """运行事件循环"""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._ws_worker())
        finally:
            try:
                self._loop.close()
            except Exception:
                pass

    async def _ws_worker(self):
        """WebSocket工作协程"""
        retry_interval = get_config("ws_retry.interval", 3)
        max_attempts = get_config("ws_retry.max_attempts", 5)
        while not self._stop_event.is_set():
            try:
                async with websockets.connect(
                        self.uri,
                        ping_interval=None,
                        max_size=None,
                        compression=None,
                        close_timeout=0.1
                ) as ws:
                    self.connected = True
                    _STATE["retry_attempts"] = 0  # 连接成功重置重试次数
                    while not self._stop_event.is_set():
                        try:
                            # 使用线程池执行队列操作，避免阻塞事件循环
                            text = await asyncio.get_event_loop().run_in_executor(
                                None,
                                lambda: self._q.get(timeout=1.0)
                            )
                            if text is None:
                                break
                            # 发送消息（只发送纯文本，树莓派会处理）
                            await ws.send(f"VOICE_RESULT:{text}")
                            # 执行回调函数（如果存在）
                            if self._callback:
                                try:
                                    self._callback(text)
                                except Exception as cb_err:
                                    console_error(f"回调函数执行异常: {cb_err}")
                        except queue.Empty:
                            continue
                        except asyncio.TimeoutError:
                            continue
                        except websockets.exceptions.ConnectionClosed as e:
                            console_error(f"WebSocket连接关闭: {str(e)}")
                            break
                        except Exception as send_err:
                            console_error(f"消息发送失败: {send_err}")
                            try:
                                self._q.put_nowait(text)
                            except Exception:
                                pass
                            break
            except OSError as e:
                self.connected = False
                _STATE["retry_attempts"] += 1
                console_error(f"第{_STATE['retry_attempts']}次连接失败: {e}")
                # 判断是否达到最大重试次数
                if _STATE["retry_attempts"] >= max_attempts:
                    console_info(f"已达到最大重试次数({max_attempts})，将自动搜索树莓派")
                    # 尝试自动发现树莓派
                    self.discovery_service.broadcast_presence()
                    # 继续尝试连接，不要退出
                    await asyncio.sleep(retry_interval)
                else:
                    console_info(
                        f"{retry_interval}秒后自动重试（剩余{max_attempts - _STATE['retry_attempts']}次）")
                    await asyncio.sleep(retry_interval)
            except Exception as e:
                self.connected = False
                console_error(f"连接异常: {str(e)}")
                await asyncio.sleep(retry_interval)
            self.connected = False


# 单例实例
_VOICE_SENDER: Optional[VoiceResultSender] = None


def get_voice_sender() -> VoiceResultSender:
    """获取语音发送器单例"""
    global _VOICE_SENDER
    if _VOICE_SENDER is None:
        _VOICE_SENDER = VoiceResultSender()
    return _VOICE_SENDER


def send_voice_result(text: str, priority: int = 0) -> bool:
    """
    快速发送语音识别结果
    Args:
        text: 语音识别结果文本
        priority: 优先级（0:普通，1:高优先级）
    Returns:
        bool: 是否成功发送
    """
    sender = get_voice_sender()
    if not sender.connected:
        # 尝试启动服务
        sender.start()
        # 等待连接建立
        for _ in range(5):
            if sender.connected:
                break
            time.sleep(1)
    return sender.send(text, priority)


def setup_voice_sender(
        auto_reconnect: bool = True,
        connection_failed_callback: Optional[Callable[[dict], None]] = None,
        connection_established_callback: Optional[Callable[[dict], None]] = None
) -> VoiceResultSender:
    """
    设置语音发送器并启动服务
    Args:
        auto_reconnect: 是否自动重连
        connection_failed_callback: 连接失败回调
        connection_established_callback: 连接建立回调
    Returns:
        VoiceResultSender: 发送器实例
    """
    sender = get_voice_sender()

    # 使用 auto_reconnect 参数
    if not auto_reconnect:
        # 如果不自动重连，设置重试次数为0
        set_config("ws_retry.max_attempts", 0)

    # 设置自定义回调
    def wrapped_callback(text: str):
        if connection_established_callback:
            conn_info = {
                "host": sender.host,
                "port": sender.port,
                "uptime": 0  # 实际实现中可以计算连接时长
            }
            connection_established_callback(conn_info)

    def connection_failed_handler(error_info: dict):
        if connection_failed_callback:
            connection_failed_callback(error_info)

    # 存储回调函数用于后续使用
    sender._connection_failed_callback = connection_failed_handler

    sender.start(wrapped_callback)
    return sender


def cleanup_voice_sender():
    """清理语音发送器资源"""
    global _VOICE_SENDER
    if _VOICE_SENDER is not None:
        _VOICE_SENDER.stop()
        _VOICE_SENDER = None


# 与pisend.py兼容的接口
def send_text_to_pi(text: str) -> bool:
    """
    兼容pisend.py的接口：发送文本到树莓派
    Args:
        text: 要发送的文本
    Returns:
        bool: 是否成功
    """
    return send_voice_result(text)


def is_pi_connected() -> bool:
    """
    检查是否与树莓派连接成功
    Returns:
        bool: 是否连接成功
    """
    sender = get_voice_sender()
    return sender.is_connected()


# 异步版本（供高级使用）
async def async_send_voice_result(text: str, priority: int = 0) -> bool:
    """
    异步发送语音识别结果
    Args:
        text: 语音识别结果文本
        priority: 优先级
    Returns:
        bool: 是否成功
    """
    sender = get_voice_sender()
    if not sender.connected:
        # 在异步环境中启动服务
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, sender.start)
        await asyncio.sleep(1)  # 等待连接建立
    return sender.send(text, priority)


# 启动网络发现服务
get_discovery_service()