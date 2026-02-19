#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pisend_receive.py - 树莓派语音接收器
功能：接收PC端发送的语音文本消息并进行语音播报
"""

import asyncio
import websockets
import threading
import time
import os
import sys
import shutil
import subprocess
import socket
from typing import Optional, Callable

# 简洁线程安全的控制台输出管理
print_lock = threading.Lock()
_status_line = ""

# 日志文件（默认放到当前用户家目录）
env_log = os.getenv('LABDETECTOR_LOG')
if env_log:
    LOG_FILE_PATH = env_log
else:
    base_default = os.path.expanduser('~/labdetector.log')
    log_dir = os.path.dirname(base_default) or os.path.expanduser('~')
    base_name = os.path.basename(base_default)
    ts = time.strftime('%Y%m%d_%H%M%S')
    LOG_FILE_PATH = os.path.join(log_dir, f"{ts}_{base_name}")

# 用于序列化文件写入的锁
log_lock = threading.Lock()


def write_log(level: str, text: str):
    """将日志写入到文件"""
    line = f"{level} {text}\n"
    try:
        # 确保日志目录存在
        log_dir_inner = os.path.dirname(LOG_FILE_PATH)
        if log_dir_inner and not os.path.exists(log_dir_inner):
            try:
                os.makedirs(log_dir_inner, exist_ok=True)
            except Exception:
                pass
        with log_lock:
            with open(LOG_FILE_PATH, 'a', encoding='utf-8') as f:
                f.write(line)
    except Exception:
        # 忽略写日志失败，避免影响主逻辑
        pass


def console_status(text: str):
    """在同一行显示实时状态（不换行）"""
    global _status_line
    with print_lock:
        _status_line = text
        # 记录到日志（状态）
        write_log('[STATUS]', text)
        try:
            print('\r' + text, end='', flush=True)
        except Exception:
            # 退化为普通输出
            print(text)


def console_info(text: str):
    """打印一条信息行，前缀 [INFO]，并尽量不破坏当前的状态行显示"""
    global _status_line
    with print_lock:
        # 清除状态行（覆盖为空格），再打印信息行
        if _status_line:
            try:
                print('\r' + ' ' * len(_status_line), end='\r', flush=True)
            except Exception:
                pass
        # 先写日志
        write_log('[INFO]', text)
        print(f"[INFO] {text}")
        # 恢复状态行显示（不换行）
        if _status_line:
            try:
                print('\r' + _status_line, end='', flush=True)
            except Exception:
                pass


def console_error(text: str):
    """打印错误信息，红色字体"""
    global _status_line
    with print_lock:
        # 清除状态行
        if _status_line:
            try:
                print('\r' + ' ' * len(_status_line), end='\r', flush=True)
            except Exception:
                pass
        # 记录到日志
        write_log('[ERROR]', text)
        # 打印错误（红色）
        print(f"\033[91m[ERROR] {text}\033[0m")
        # 恢复状态行
        if _status_line:
            try:
                print('\r' + _status_line, end='', flush=True)
            except Exception:
                pass


# ====================== TTS (text-to-speech) 支持 ======================
_TTS_ENGINE = None
tts_queue = None
tts_task = None


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
        except Exception:
            return "127.0.0.1"


def init_tts() -> bool:
    """初始化TTS：优先使用espeak（轻量且常见），失败时使用pyttsx3"""
    global _TTS_ENGINE

    try:
        # 在树莓派/Linux上优先使用espeak
        if sys.platform.startswith("linux"):
            if shutil.which("espeak") is not None:
                _TTS_ENGINE = "espeak"
                console_info("TTS: 使用 espeak（Linux 优先）")
                return True

        # 尝试使用pyttsx3
        try:
            import pyttsx3
            engine = pyttsx3.init()
            engine.setProperty('rate', 150)
            engine.setProperty('volume', 1.0)
            _TTS_ENGINE = engine
            console_info("TTS: 使用 pyttsx3（回退）")
            return True
        except Exception:
            pass

        # 最后一次尝试检测espeak
        if shutil.which("espeak") is not None:
            _TTS_ENGINE = "espeak"
            console_info("TTS: 使用 espeak 回退")
            return True
    except Exception as e:
        console_error(f"TTS初始化异常: {str(e)}")

    console_info("未检测到 pyttsx3 或 espeak，文字播报功能将不可用")
    _TTS_ENGINE = None
    return False


def speak_async(text: str):
    """异步播报文本（非阻塞）"""

    def _speak(t):
        global _TTS_ENGINE
        if not t or _TTS_ENGINE is None:
            return
        try:
            if _TTS_ENGINE == "espeak":
                # 使用系统命令播报（Linux）
                subprocess.run(["espeak", "-v", "zh", t],
                               stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)
            elif hasattr(_TTS_ENGINE, 'say'):
                # pyttsx3 engine
                try:
                    _TTS_ENGINE.say(t)
                    if hasattr(_TTS_ENGINE, 'runAndWait'):
                        _TTS_ENGINE.runAndWait()
                except Exception as e:
                    console_error(f"pyttsx3播报异常: {str(e)}")
            else:
                # 无可用TTS
                pass
        except Exception as e:
            console_error(f"TTS播报异常: {str(e)}")

    threading.Thread(target=_speak, args=(text,), daemon=True).start()


def speak_enqueue(text: str):
    """将文本加入TTS队列（非阻塞）"""
    global tts_queue
    if tts_queue is None:
        # 回退：直接播放
        speak_async(text)
        return
    try:
        # 不等待，尽量快速入队
        tts_queue.put_nowait(text)
    except asyncio.QueueFull:
        console_error("消息队列已满")
    except Exception as e:
        console_error(f"消息入队失败: {str(e)}")
        # 队列满或异常，回退播放
        speak_async(text)


async def tts_worker():
    """串行的TTS消费者，确保语音按顺序播放且不重叠"""
    global tts_queue
    while True:
        try:
            text = await tts_queue.get()
            if text is None:
                break
            # 播报文本
            speak_async(text)
        except asyncio.CancelledError:
            break
        except Exception as e:
            console_error(f"TTS工作异常: {str(e)}")
            continue


# ====================== WebSocket服务 ======================
async def handle_client(websocket, path):
    """处理客户端连接"""
    console_info(f"📱 PC客户端已连接: {websocket.remote_address}")

    try:
        while True:
            # 接收消息
            msg = await websocket.recv()

            # 处理文本消息
            if isinstance(msg, str):
                text = msg.strip()
                if text:
                    # 检查是否是语音消息（以[voice]开头）
                    if text.startswith("[voice]"):
                        text = text[7:]  # 移除[voice]前缀
                        console_info(f"📨 接收到语音播报请求: {text}")
                        # 将文本加入TTS队列
                        speak_enqueue(text)
                    else:
                        console_info(f"📨 接收到消息: {text}")
    except websockets.exceptions.ConnectionClosed:
        console_info(f"🔌 PC客户端断开连接: {websocket.remote_address}")
    except Exception as e:
        console_error(f"❌ 客户端连接异常: {str(e)}")


async def start_server():
    """启动WebSocket服务器"""
    host = "0.0.0.0"  # 监听所有接口
    port = 8001

    console_info(f"🌐 启动WebSocket服务器: ws://0.0.0.0:{port}")
    console_info(f"ℹ️  本机IP地址: {get_local_ip()}")

    server = await websockets.serve(
        handle_client,
        host,
        port,
        ping_interval=None,
        max_size=None,
        compression=None,
        close_timeout=0.1
    )

    console_info("✅ WebSocket服务器已启动，等待PC连接...")
    await server.wait_closed()


async def safe_start():
    """安全启动服务器"""
    global tts_queue, tts_task

    # 初始化TTS
    if init_tts():
        # 创建TTS队列和任务
        tts_queue = asyncio.Queue(maxsize=16)
        tts_task = asyncio.create_task(tts_worker())

    # 输出日志文件路径
    console_info(f"📁 日志文件路径: {LOG_FILE_PATH}")

    try:
        await start_server()
    except Exception as e:
        console_error(f"❌ 服务器启动异常: {str(e)}")


# ====================== 主程序 ======================
if __name__ == "__main__":
    console_info("=" * 50)
    console_info("树莓派语音接收器 v1.0")
    console_info("=" * 50)

    try:
        # 启动事件循环
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(safe_start())
    except KeyboardInterrupt:
        console_info("⏹️  服务已手动停止")
    except Exception as e:
        console_error(f"❌ 主程序异常: {str(e)}")
    finally:
        # 清理资源
        try:
            if tts_queue is not None:
                tts_queue.put_nowait(None)
            if tts_task is not None:
                tts_task.cancel()
                try:
                    loop.run_until_complete(tts_task)
                except asyncio.CancelledError:
                    pass
        except Exception as e:
            console_error(f"资源清理异常: {str(e)}")
        console_info("🧹 资源清理完成")
        console_info("🔚 程序已退出")