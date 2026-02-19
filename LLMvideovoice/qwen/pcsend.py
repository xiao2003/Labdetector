#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import asyncio
import websockets
import threading
import queue
import time
import os
import sys
from typing import Optional, Callable, Dict, Any

# 全局配置（与Pi_llm_voice.py保持一致）
CONFIG = {
    "websocket": {"host": "192.168.31.31", "port": 8001},  # 树莓派WS地址
    "ws_retry": {
        "max_attempts": 5,  # 最大重试次数
        "interval": 3,  # 基础重试间隔（秒）
        "backoff_factor": 2,  # 退避因子
        "max_delay": 30  # 最大延迟时间
    },
    "connection": {
        "timeout": 10,  # 连接超时时间
        "heartbeat_interval": 30  # 心跳检测间隔
    }
}


class VoiceResultSender:
    """语音识别结果发送器 - 专门用于向树莓派发送语音识别结果"""

    def __init__(self):
        self.host = CONFIG["websocket"]["host"]
        self.port = CONFIG["websocket"]["port"]
        self.uri = f"ws://{self.host}:{self.port}"
        self._q: queue.Queue = queue.Queue(maxsize=20)  # 限制队列大小
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self.connected = False
        self._stop_event = threading.Event()
        self._auto_reconnect = True
        self._connection_failed_callback: Optional[Callable[[Dict[str, Any]], None]] = None
        self._connection_established_callback: Optional[Callable[[Dict[str, Any]], None]] = None
        self._heartbeat_task = None
        self._last_heartbeat = time.time()
        self._connection_attempts = 0
        self._connection_start_time = None
        self._total_uptime = 0
        self._last_send_time = 0
        self._send_count = 0
        self._failed_send_count = 0

    def start(self,
              auto_reconnect: bool = True,
              connection_failed_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
              connection_established_callback: Optional[Callable[[Dict[str, Any]], None]] = None) -> bool:
        """启动发送服务"""
        if self._thread and self._thread.is_alive():
            return True

        self._auto_reconnect = auto_reconnect
        self._connection_failed_callback = connection_failed_callback
        self._connection_established_callback = connection_established_callback
        self._stop_event.clear()

        try:
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()
            return True
        except Exception:
            return False

    def stop(self, cleanup: bool = True):
        """停止发送服务"""
        self._auto_reconnect = False
        self._stop_event.set()

        # 清理队列
        if cleanup:
            while not self._q.empty():
                try:
                    self._q.get_nowait()
                except queue.Empty:
                    break

        # 发送停止信号
        try:
            self._q.put_nowait(None)
        except Exception:
            pass

        # 等待线程结束
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)

        # 清理心跳任务
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            self._heartbeat_task = None

        self.connected = False

    def send(self, text: str, priority: int = 0) -> bool:
        """
        发送语音识别结果到树莓派
        Args:
            text: 要发送的文本内容
            priority: 优先级（0:普通，1:高优先级）
        Returns:
            bool: 是否成功入队
        """
        if not text:
            return False

        try:
            # 高优先级消息插入队列头部
            if priority == 1:
                # 使用临时队列实现优先级插入
                temp_queue = queue.Queue()
                while not self._q.empty():
                    item = self._q.get_nowait()
                    if item is not None:  # 避免处理停止信号
                        temp_queue.put(item)

                self._q.put(text)
                while not temp_queue.empty():
                    self._q.put(temp_queue.get_nowait())
            else:
                self._q.put_nowait(text)

            return True
        except queue.Full:
            return False
        except Exception:
            return False

    def _run_loop(self):
        """运行事件循环"""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._ws_worker())
        finally:
            try:
                if self._loop and self._loop.is_running():
                    self._loop.stop()
                if self._loop and not self._loop.is_closed():
                    self._loop.close()
            except Exception:
                pass

    async def _ws_worker(self):
        """WebSocket工作协程（精简版）"""
        retry_interval = CONFIG["ws_retry"]["interval"]
        max_attempts = CONFIG["ws_retry"]["max_attempts"]
        backoff_factor = CONFIG["ws_retry"]["backoff_factor"]
        max_delay = CONFIG["ws_retry"]["max_delay"]

        while not self._stop_event.is_set():
            try:
                # 使用带超时的连接
                ws_conn = await asyncio.wait_for(
                    websockets.connect(
                        self.uri,
                        ping_interval=None,
                        max_size=None,
                        compression=None,
                        close_timeout=0.1,
                        open_timeout=CONFIG["connection"]["timeout"]
                    ),
                    timeout=CONFIG["connection"]["timeout"]
                )

                # 连接成功
                self.connected = True
                self._connection_attempts = 0

                # 通知连接建立回调
                if self._connection_established_callback:
                    try:
                        conn_info = {
                            "host": self.host,
                            "port": self.port,
                            "timestamp": time.time(),
                            "uptime": 0
                        }
                        self._connection_established_callback(conn_info)
                    except Exception:
                        pass

                # 主消息循环
                while not self._stop_event.is_set() and self.connected:
                    try:
                        text = await asyncio.wait_for(
                            self._get_from_queue(),
                            timeout=1.0
                        )
                        if text is None:
                            break  # 停止信号

                        # 发送消息
                        await ws_conn.send(f"VOICE_RESULT:{text}")
                        self._last_heartbeat = time.time()
                    except asyncio.TimeoutError:
                        continue
                    except queue.Empty:
                        continue
                    except Exception:
                        try:
                            self._q.put_nowait(text)
                        except Exception:
                            pass
                        break
                    except websockets.exceptions.ConnectionClosed:
                        self.connected = False
                        break

                # 清理连接
                try:
                    await ws_conn.close()
                except:
                    pass
            except Exception:
                self.connected = False
                self._connection_attempts += 1

                # 通知连接失败回调
                if self._connection_failed_callback and self._connection_attempts >= max_attempts:
                    try:
                        error_info = {
                            "host": self.host,
                            "port": self.port,
                            "timestamp": time.time(),
                            "attempts": self._connection_attempts,
                            "max_attempts": max_attempts,
                            "error": "connection failed"
                        }
                        self._connection_failed_callback(error_info)
                    except Exception:
                        pass

                # 指数退避重试
                if self._auto_reconnect and self._connection_attempts < max_attempts:
                    wait_time = min(retry_interval * (backoff_factor ** (self._connection_attempts - 1)), max_delay)
                    await asyncio.sleep(wait_time)
                else:
                    break

    async def _get_from_queue(self):
        """从队列获取项目，处理停止信号"""
        try:
            item = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._q.get(timeout=0.5)
            )
            return item
        except queue.Empty:
            return None

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
    # 只有在连接成功时才尝试发送
    if sender.connected:
        return sender.send(text, priority)
    return False


def setup_voice_sender(
        auto_reconnect: bool = True,
        connection_failed_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        connection_established_callback: Optional[Callable[[Dict[str, Any]], None]] = None
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
    sender.start(
        auto_reconnect=auto_reconnect,
        connection_failed_callback=connection_failed_callback,
        connection_established_callback=connection_established_callback
    )
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