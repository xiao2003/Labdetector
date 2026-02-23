#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pisend_receive.py - 树莓派全双工收发器 (支持 QoS 动态帧率均衡版)
"""
import asyncio
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time

import cv2
import websockets

from pcside.core.voice_interaction import pyaudio
from tools.version_manager import get_app_version
from voice.interaction import PiVoiceInteraction
from voice.recognizer import PiVoiceRecognizer

APP_VERSION = get_app_version()

try:
    from picamera2 import Picamera2

    PICAMERA_AVAILABLE = True
except ImportError:
    PICAMERA_AVAILABLE = False

from tools.model_downloader import check_and_download_vosk

check_and_download_vosk()

# 全局运行状态与日志
LOG_FILE_PATH = os.path.join(os.getcwd(), f"{time.strftime('%Y%m%d_%H%M%S')}_运行日志.txt")
log_lock = threading.Lock()
running = True

# ★ 默认帧率状态字典，可被 PC 动态修改 ★
_PI_STATE = {
    "sleep_time": 0.033  # 默认 30fps = 1/30
}


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


picam2 = None


async def get_frame():
    if not picam2: return None
    try:
        return await asyncio.wait_for(asyncio.to_thread(picam2.capture_array), timeout=1.0)
    except:
        return None


async def handle_client(websocket, path=""):
    console_info(f"📱 PC连接成功: {websocket.remote_address}")

    async def recv_loop():
        try:
            async for msg in websocket:
                # ★ 核心拦截：动态调配 QoS 指令 ★
                if isinstance(msg, str) and msg.startswith("CMD:SET_FPS:"):
                    try:
                        target_fps = float(msg.split(":")[-1])
                        _PI_STATE["sleep_time"] = 1.0 / max(1.0, target_fps)
                        console_info(
                            f"⚙️ 收到主控动态调配: 调整为 {target_fps:.1f} FPS (休眠 {_PI_STATE['sleep_time']:.3f}s)")
                    except Exception as e:
                        console_error(f"解析帧率指令失败: {e}")
                    continue

                # 普通文本则是 TTS 播报
                text = msg.replace("VOICE_RESULT:", "").strip()
                print(f"\n\033[92m[主机回报:] {text}\033[0m\n")
                write_log("[AI]", text)
                if tts_queue: await tts_queue.put(text)
        except websockets.exceptions.ConnectionClosed:
            pass
        except Exception as e:
            console_error(f"指令接收中断: {e}")

    async def send_loop():
        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 60]
        try:
            while running:
                # ★ 核心：动态休眠 ★
                await asyncio.sleep(_PI_STATE["sleep_time"])

                frame = await get_frame()
                if frame is not None:
                    flipped = cv2.flip(frame, 0)
                    resized = cv2.resize(flipped, (640, 480))
                    ret, buf = cv2.imencode('.jpg', resized, encode_param)
                    if ret:
                        await websocket.send(buf.tobytes())
        except websockets.exceptions.ConnectionClosed:
            pass
        except Exception as e:
            console_error(f"视频推送异常: {e}")

    done, pending = await asyncio.wait(
        [asyncio.create_task(recv_loop()), asyncio.create_task(send_loop())],
        return_when=asyncio.FIRST_COMPLETED
    )
    for t in pending: t.cancel()
    console_info("🔌 客户端连接已平滑关闭")


async def main_async():
    global picam2, tts_queue, running
    NetworkDiscoveryResponder().start()

    if PICAMERA_AVAILABLE:
        try:
            picam2 = Picamera2()
            config = picam2.create_video_configuration(main={"size": (1280, 720), "format": "RGB888"})
            picam2.configure(config)
            picam2.start()
            console_info("✅ Picamera2 硬件初始化成功")
        except Exception as e:
            console_error(f"摄像头启动失败: {e}")

    if init_tts():
        tts_queue = asyncio.Queue()

        async def _tts_worker():
            while running:
                txt = await tts_queue.get()
                speak_async(txt)

        asyncio.create_task(_tts_worker())

    async with websockets.serve(handle_client, "0.0.0.0", 8001, ping_interval=20, ping_timeout=20, max_size=None):
        console_info(f"🌐 WebSocket服务已就绪 ws://{get_local_ip()}:8001")
        while running: await asyncio.sleep(1)


def main():
    global running
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        loop.create_task(main_async())
    else:
        try:
            asyncio.run(main_async())
        except KeyboardInterrupt:
            running = False


async def voice_thread(websocket):
    """独立的语音采集与识别协程"""
    # 初始化
    model_dir = os.path.join(os.path.dirname(__file__), "voice", "model")
    recognizer = PiVoiceRecognizer(model_dir)
    interaction = PiVoiceInteraction(recognizer)

    # 开启麦克风
    p = pyaudio.PyAudio()
    stream = p.open(format=pyaudio.paInt16, channels=1, rate=16000,
                    input=True, frames_per_buffer=4000)
    stream.start_stream()

    console_info("🎤 Pi端本地语音引擎已就绪")

    while running:
        # 读取音频数据
        data = await asyncio.to_thread(stream.read, 4000, exception_on_overflow=False)

        # 交给交互模块处理
        event = interaction.process_audio(data)

        if event == "EVENT:WOKEN":
            speak_async("我在。")  # 本地先响应
            await websocket.send("PI_EVENT:WOKEN")  # 通知 PC 联动
        elif event and event.startswith("CMD_TEXT:"):
            cmd_text = event.replace("CMD_TEXT:", "")
            console_info(f"🗣️ 识别到指令: {cmd_text}")

            # ★ 核心：回传给 PC ★
            await websocket.send(f"PI_VOICE_COMMAND:{cmd_text}")
            interaction.is_active = False  # 完成一次指令后回到待机

    stream.stop_stream()
    stream.close()


def run_pi_self_check():
    """执行 Pi 边缘节点预检"""
    print("\n" + "=" * 50)
    print(f"[INFO] LabDetector V{APP_VERSION} (Pi 边缘端) - 节点自检")
    print("=" * 50)

    # ---------------------------------------------------------
    # [1/3] 依赖与环境自检
    # ---------------------------------------------------------
    print("\n[INFO] [1/3] 检查边缘端依赖环境...")
    try:
        import websockets
        import cv2
        import pyaudio
        import vosk
        print("[INFO]   核心通信与语音依赖包已就绪.")
    except ImportError as e:
        print(f"[ERROR]   缺少依赖: {e}")
        print("[INFO]   请先运行: pip install -e .")
        sys.exit(1)

    # ---------------------------------------------------------
    # [2/3] 摄像头硬件自检
    # ---------------------------------------------------------
    print("\n[INFO] [2/3] 检查摄像头硬件...")
    if PICAMERA_AVAILABLE:
        print("[INFO]   Picamera2 模块加载成功，原生摄像头就绪.")
    else:
        print("[WARN]   Picamera2 不可用，将尝试使用 OpenCV 备用捕捉模块.")

    # ---------------------------------------------------------
    # [3/3] 离线语音唤醒模型自检
    # ---------------------------------------------------------
    print("\n[INFO] [3/3] 检查 Vosk 离线唤醒模型...")
    try:
        from tools.model_downloader import check_and_download_vosk
        check_and_download_vosk()
    except ImportError:
        print("[WARN] 未找到 tools/model_downloader.py，跳过模型自检.")

    print("\n" + "=" * 50)
    print("[INFO] 边缘节点自检完成，正在尝试接入中枢集群...")
    print("=" * 50 + "\n")
    time.sleep(1)


if __name__ == '__main__':
    run_pi_self_check()

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        loop.create_task(main_async())
    else:
        try:
            asyncio.run(main_async())
        except KeyboardInterrupt:
            running = False
            print("\n[INFO] 正在关闭 Pi 边缘节点...")
