#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
main.py - 主程序入口 (异步优化 + 完整模型列表版)
"""
import asyncio
import cv2
import numpy as np
import threading
import subprocess
import ctypes
import sys
import os
import time
import socket
import signal
import queue
from typing import Optional

import requests
import websockets

# ==================== 尝试导入核心模块 ====================
try:
    from core.config import get_config, set_config
    from core.logger import console_info, console_error, console_prompt
    from core.tts import speak_async
    from core.voice_interaction import get_voice_interaction, is_voice_interaction_available, VoiceInteractionConfig
    from core.ai_backend import list_ollama_models, analyze_image
    from communication.pcsend import setup_voice_sender, send_voice_result, cleanup_voice_sender
    from core.network import get_local_ip, get_network_prefix
except ImportError:
    # 模拟/回退实现 (当环境配置不正确时)
    def console_info(text: str):
        print(f"[INFO] {text}")


    def console_error(text: str):
        print(f"[ERROR] {text}")


    def console_prompt(text: str):
        print(text)


    def speak_async(text: str):
        print(f"[SPEAK] {text}")


    def get_config(key_path: str, default=None):
        parts = key_path.split('.')
        if parts[0] == "camera" and parts[1] == "resolution":
            return 1280 if parts[2] == "0" else 720
        elif parts[0] == "ollama" and parts[1] == "default_models":
            return ["llava:7b-v1.5-q4_K_M", "llava:13b-v1.5-q4_K_M", "llava:34b-v1.5-q4_K_M", "llava:latest"]
        elif parts[0] == "websocket":
            return "192.168.31.31" if parts[1] == "host" else 8001
        elif parts[0] == "inference" and parts[1] == "interval":
            return 5
        elif parts[0] == "display":
            return 1280 if parts[1] == "width" else 720
        return default


    def set_config(key_path: str, value):
        pass


    def list_ollama_models():
        return []


    def analyze_image(frame, model, backend):
        return "识别结果"


    def is_voice_interaction_available():
        return False


    def get_voice_interaction(config):
        return None


    def setup_voice_sender(*args, **kwargs):
        pass


    def send_voice_result(text, priority=0):
        return True


    def cleanup_voice_sender():
        pass


    def get_local_ip():
        return "127.0.0.1"


    def get_network_prefix():
        return "192.168.1."

# ==================== 全局状态与队列 ====================
_STATE = {
    "running": True,
    "mode": "",
    "frame_buffer": None,
    "selected_model": "",
    "ai_backend": "",
    "ws_connected": False
}

# 异步推理队列 (maxsize=1 保证只处理最新帧)
inference_queue = queue.Queue(maxsize=1)
# 存储最新推理结果，供主线程 UI 渲染
latest_inference_result = {"text": "", "timestamp": 0}


# ==================== 异步推理线程 ====================
class InferenceThread(threading.Thread):
    def __init__(self, interval, backend, model):
        super().__init__(daemon=True)
        self.interval = interval
        self.backend = backend
        self.model = model
        self.running = True

    def run(self):
        console_info(f"🚀 AI后台推理线程启动 (引擎: {self.backend}, 间隔: {self.interval}s)")
        last_infer_time = 0

        while self.running and _STATE["running"]:
            try:
                frame = inference_queue.get(timeout=0.1)
                current_time = time.time()

                if current_time - last_infer_time < self.interval:
                    continue

                if frame is None or np.all(frame == 0):
                    continue

                # 执行耗时推理
                result = analyze_image(frame, self.model, self.backend)

                if result and result != "识别失败":
                    latest_inference_result["text"] = result
                    latest_inference_result["timestamp"] = time.time()

                    # 语音或远程发送
                    if _STATE["mode"] == "websocket":
                        send_voice_result(result)
                    else:
                        speak_async(result)

                last_infer_time = time.time()

            except queue.Empty:
                continue
            except Exception as e:
                console_error(f"推理线程异常: {str(e)}")
                time.sleep(1)

    def stop(self):
        self.running = False


# ==================== 辅助功能 ====================
def is_admin():
    return os.name != 'nt' or ctypes.windll.shell32.IsUserAnAdmin()


def run_as_admin():
    if os.name != 'nt' or is_admin(): return True
    try:
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(sys.argv), None, 1)
        return False
    except:
        return False


def select_ai_backend():
    console_prompt("\n===== AI后端选择 =====")
    console_prompt("1. Ollama (本地模型)")
    console_prompt("2. Qwen3.5-Plus (云端模型)")
    while True:
        choice = input("\n请选择 (1/2): ").strip()
        if choice == "1":
            _STATE["ai_backend"] = "ollama"
            return True
        elif choice == "2":
            _STATE["ai_backend"] = "qwen"
            return True


def select_model():
    if _STATE["ai_backend"] == "qwen":
        _STATE["selected_model"] = "qwen-vl-max"
        return True

    console_prompt("\n===== 模型选择 =====")
    local_models = list_ollama_models()
    default_models = get_config("ollama.default_models", ["llava:7b-v1.5-q4_K_M"])

    all_models = list(set(default_models + local_models))
    all_models.sort()

    for idx, model in enumerate(all_models, 1):
        status = "[已安装]" if model in local_models else "[未安装]"
        console_prompt(f"{idx}. {model} {status}")
    console_prompt(f"{len(all_models) + 1}. 自定义模型")

    while True:
        choice = input("\n请输入序号: ").strip()
        if choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(all_models):
                _STATE["selected_model"] = all_models[idx - 1]
                break
            elif idx == len(all_models) + 1:
                _STATE["selected_model"] = input("请输入模型名: ").strip()
                break
    return True


# ==================== 视频源线程 ====================
def camera_worker():
    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    while _STATE["running"] and _STATE["mode"] == "camera":
        ret, frame = cap.read()
        if ret: _STATE["frame_buffer"] = frame.copy()
        time.sleep(0.01)
    cap.release()


async def websocket_client():
    uri = f"ws://{get_config('websocket.host')}:{get_config('websocket.port')}"
    while _STATE["running"] and _STATE["mode"] == "websocket":
        try:
            async with websockets.connect(uri, ping_interval=None) as ws:
                console_info("已连接到树莓派视频流")
                while _STATE["running"] and _STATE["mode"] == "websocket":
                    data = await asyncio.wait_for(ws.recv(), timeout=1.0)
                    nparr = np.frombuffer(data, np.uint8)
                    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                    if frame is not None:
                        _STATE["frame_buffer"] = cv2.resize(frame, (1280, 720))
        except:
            await asyncio.sleep(2)


def start_video_source():
    if _STATE["mode"] == "camera":
        threading.Thread(target=camera_worker, daemon=True).start()
    else:
        def _run():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(websocket_client())

        threading.Thread(target=_run, daemon=True).start()


# ==================== 主流程 ====================
def main():
    def signal_handler(sig, frame):
        _STATE["running"] = False
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)

    if not run_as_admin(): return

    _STATE["frame_buffer"] = np.zeros((720, 1280, 3), np.uint8)

    if not select_ai_backend(): return

    console_prompt("\n===== 模式选择 =====")
    console_prompt("1. 本机摄像头 | 2. 树莓派WS")
    _STATE["mode"] = "camera" if input("请选择 (1/2): ").strip() == "1" else "websocket"

    if not select_model(): return

    if _STATE["ai_backend"] == "ollama":
        subprocess.run(f"ollama pull {_STATE['selected_model']}", shell=True)
        subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(2)

    if _STATE["mode"] == "websocket": setup_voice_sender(auto_reconnect=True)

    start_video_source()

    # 启动异步推理
    inference_thread = InferenceThread(
        interval=get_config("inference.interval", 5),
        backend=_STATE["ai_backend"],
        model=_STATE["selected_model"]
    )
    inference_thread.start()

    cv2.namedWindow("Analysis", cv2.WINDOW_NORMAL)

    while _STATE["running"]:
        if _STATE["frame_buffer"] is not None:
            display_frame = _STATE["frame_buffer"].copy()

            # UI 渲染识别结果
            text = latest_inference_result["text"]
            if text and (time.time() - latest_inference_result["timestamp"] < 10):
                cv2.rectangle(display_frame, (10, 10), (600, 60), (0, 0, 0), -1)
                cv2.putText(display_frame, f"AI: {text}", (20, 45),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)

            cv2.imshow("Analysis", display_frame)

            # 更新推理队列
            if not inference_queue.full():
                inference_queue.put(display_frame)
            else:
                try:
                    inference_queue.get_nowait()
                    inference_queue.put_nowait(display_frame)
                except:
                    pass

        if cv2.waitKey(1) & 0xFF == ord('q'): break

    _STATE["running"] = False
    cv2.destroyAllWindows()
    cleanup_voice_sender()


if __name__ == "__main__":
    main()