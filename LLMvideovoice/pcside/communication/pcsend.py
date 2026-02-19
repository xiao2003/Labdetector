#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import asyncio
import websockets
import threading
import queue
import time
import sys
from typing import Optional, Callable
# 从同一目录导入网络发现模块
from .network_discovery import get_discovery_service

# 尝试导入核心模块
try:
    from core.config import set_config
    from core.logger import console_info, console_error, console_status
except ImportError:
    try:
        from .config import set_config
        from .logger import console_info, console_error, console_status
    except ImportError:
        # 定义简单的替代函数
        def console_info(text: str):
            print(f"[INFO] {text}")


        def console_error(text: str):
            import time
            print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} [ERROR] {text}")


        def console_status(text: str):
            print(text)


        def set_config(key_path: str, value):
            """模拟的set_config函数"""
            console_info(f"模拟设置配置: {key_path} = {value}")

# 全局配置（与Pi_llm_voice.py保持一致）
CONFIG = {
    "websocket": {"host": "192.168.31.31", "port": 8001},  # 树莓派WS地址
    "ws_retry": {"max_attempts": 5, "interval": 3}  # WS重试配置
}

# 全局状态
_STATE = {
    "running": True,
    "connected": False,
    "ws_loop": None,
    "ws_task": None,
    "retry_attempts": 0
}


class VoiceResultSender:
    """语音识别结果发送器 - 专门用于向树莓派发送语音识别结果"""

    def __init__(self):
        self.host = CONFIG["websocket"]["host"]
        self.port = CONFIG["websocket"]["port"]
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
        try:
            set_config("websocket.host", pi_ip)
        except Exception as e:
            console_error(f"更新WebSocket配置失败: {str(e)}")
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
        retry_interval = CONFIG["ws_retry"]["interval"]
        max_attempts = CONFIG["ws_retry"]["max_attempts"]
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
                            # 发送消息
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
                    break
                else:
                    console_info(
                        f"{retry_interval}秒后自动重试（剩余{max_attempts - _STATE['retry_attempts']}次）")
                    await asyncio.sleep(retry_interval)
            except Exception as e:
                self.connected = False
                console_error(f"连接异常: {str(e)}")
                await asyncio.sleep(retry_interval)
            self.connected = False

    def is_connected(self) -> bool:
        """检查是否连接成功"""
        return self.connected


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
        CONFIG["ws_retry"]["max_attempts"] = 0

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