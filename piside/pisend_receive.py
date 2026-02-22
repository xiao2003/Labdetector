#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pisend_receive.py - 树莓派全双工收发器 (智能环境适配 + 极速响应版)
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
import json
import cv2
import numpy as np
from typing import Optional, Any

try:
    from picamera2 import Picamera2

    PICAMERA_AVAILABLE = True
except ImportError:
    PICAMERA_AVAILABLE = False

# ====================== 日志与系统控制 ======================
LOG_FILE_PATH = os.path.join(os.getcwd(), f"{time.strftime('%Y%m%d_%H%M%S')}_运行日志.txt")
log_lock = threading.Lock()
running = True


def write_log(level: str, text: str):
    try:
        log_line = f"[{time.strftime('%H:%M:%S')}] {level} {text}\n"
        with log_lock:
            with open(LOG_FILE_PATH, 'a', encoding='utf-8') as f: f.write(log_line)
    except:
        pass


def console_info(text: str):
    write_log('[INFO]', text)
    print(f"[INFO] {text}")


def console_error(text: str):
    write_log('[ERROR]', text)
    print(f"\033[91m[ERROR] {text}\033[0m")


def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        res = s.getsockname()[0]
        s.close()
        return res
    except:
        return "127.0.0.1"


# ====================== TTS 与发现服务 ======================
_TTS_ENGINE = None
tts_queue = None


def init_tts():
    global _TTS_ENGINE
    try:
        if sys.platform.startswith("linux") and shutil.which("espeak"):
            _TTS_ENGINE = "espeak"
            return True
        import pyttsx3
        _TTS_ENGINE = pyttsx3.init()
        return True
    except:
        return False


def speak_async(text):
    def _speak(t):
        if not t or not _TTS_ENGINE: return
        try:
            if _TTS_ENGINE == "espeak":
                cmd = shutil.which("espeak")
                if cmd: subprocess.run([str(cmd), "-v", "zh", t], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                _TTS_ENGINE.say(t)
                _TTS_ENGINE.runAndWait()
        except:
            pass

    threading.Thread(target=_speak, args=(text,), daemon=True).start()


class NetworkDiscoveryResponder:
    def __init__(self):
        self.port = 50000
        self.local_ip = get_local_ip()

    def start(self):
        def _loop():
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("", self.port))
                while running:
                    try:
                        data, addr = sock.recvfrom(1024)
                        if json.loads(data.decode())['type'] == 'pc_discovery':
                            resp = json.dumps({'type': 'raspberry_pi_response', 'ip': self.local_ip})
                            sock.sendto(resp.encode(), addr)
                    except:
                        pass
            finally:
                sock.close()

        threading.Thread(target=_loop, daemon=True).start()
        console_info(f"UDP 发现服务已就绪 (端口: {self.port})")


# ====================== WebSocket 硬件全双工核心逻辑 ======================
picam2 = None


async def get_frame():
    """极致轻量化的画面捕获"""
    if not picam2: return None
    try:
        # 使用 to_thread 保证 libcamera 的同步 IO 不会阻塞 Asyncio 心跳
        return await asyncio.to_thread(picam2.capture_array)
    except:
        return None


async def handle_client(websocket, path=""):
    console_info(f"📱 PC连接成功: {websocket.remote_address}")

    async def recv_loop():
        """持续接收 PC AI 结果"""
        try:
            async for msg in websocket:
                text = msg.replace("VOICE_RESULT:", "").strip()
                print(f"\n\033[92m[主机回报:] {text}\033[0m\n")
                write_log("[AI]", text)
                if tts_queue: await tts_queue.put(text)
        except Exception as e:
            console_error(f"指令接收中断: {e}")

    async def send_loop():
        """持续推送视频帧"""
        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 65]
        try:
            while running:
                frame = await get_frame()
                if frame is not None:
                    # 翻转并编码
                    flipped = cv2.flip(frame, 0)
                    ret, buf = cv2.imencode('.jpg', flipped, encode_param)
                    if ret:
                        await websocket.send(buf.tobytes())
                # 稳定在 20FPS 左右，降低系统负载
                await asyncio.sleep(0.04)
        except Exception as e:
            console_error(f"视频推送中断: {e}")

    # 同时运行两个任务，直到任意一个任务出错（如 PC 断开）
    done, pending = await asyncio.wait(
        [asyncio.create_task(recv_loop()), asyncio.create_task(send_loop())],
        return_when=asyncio.FIRST_COMPLETED
    )
    for t in pending: t.cancel()
    console_info("🔌 客户端连接已关闭")


async def main_async():
    global picam2, tts_queue, running

    # 1. 启动广播发现
    NetworkDiscoveryResponder().start()

    # 2. 初始化相机硬件
    if PICAMERA_AVAILABLE:
        try:
            picam2 = Picamera2()
            config = picam2.create_video_configuration(main={"size": (1280, 720), "format": "RGB888"})
            picam2.configure(config)
            picam2.start()
            console_info("✅ 摄像头 Picamera2 硬件初始化成功")
        except Exception as e:
            console_error(f"摄像头启动失败: {e}")

    # 3. 初始化文本播报
    if init_tts():
        tts_queue = asyncio.Queue()

        async def _tts_worker():
            while running:
                txt = await tts_queue.get()
                speak_async(txt)

        asyncio.create_task(_tts_worker())

    # 4. 启动 WebSocket 服务
    async with websockets.serve(handle_client, "0.0.0.0", 8001, ping_interval=None):
        console_info(f"🌐 WebSocket服务已就绪 ws://{get_local_ip()}:8001")
        while running:
            await asyncio.sleep(1)


def main():
    global running
    # ★ 核心修复：智能环境检测启动 ★
    try:
        # 尝试获取当前环境中是否已经有事件循环在跑
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # 如果在 Thonny/Notebook 等环境下，直接把主任务塞进去
        console_info("检测到已运行的事件循环，任务已注入。")
        loop.create_task(main_async())
    else:
        # 如果是命令行纯 Python 环境，开启新循环
        try:
            asyncio.run(main_async())
        except KeyboardInterrupt:
            running = False
            print(f"\n✅ 程序结束，日志已导出: {LOG_FILE_PATH}")


if __name__ == "__main__":
    main()