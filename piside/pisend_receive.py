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
import uuid

import cv2
import websockets

import base64
from edge_vision.motion_detector import EdgeMotionDetector
from edge_vision.adaptive_capture import AdaptiveCaptureController
import pyaudio

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
    "sleep_time": 0.033,  # 默认 30fps = 1/30
    "policies": [],  # 新增：缓存策略
    "has_mic": False,
    "has_speaker": False,
    "expert_results": {},
    "storage_budget_mb_per_hour": 500.0
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
    print(text if text.startswith("[INFO]") else f"[INFO] {text}")


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


def detect_audio_capabilities():
    """检测 Pi 端音频能力（麦克风/扬声器）。"""
    has_mic, has_speaker = False, False
    try:
        p = pyaudio.PyAudio()
        try:
            has_mic = p.get_default_input_device_info() is not None
        except Exception:
            has_mic = False
        try:
            has_speaker = p.get_default_output_device_info() is not None
        except Exception:
            has_speaker = False
        p.terminate()
    except Exception:
        pass
    return has_mic, has_speaker


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
    capture_controller = AdaptiveCaptureController()
    console_info(f"[INFO] PC连接成功: {websocket.remote_address}")

    await websocket.send(f"PI_CAPS:{json.dumps({'has_mic': _PI_STATE['has_mic'], 'has_speaker': _PI_STATE['has_speaker']})}")

    # ★ 新增：启动语音协程，共用当前的 websocket 连接
    voice_task = asyncio.create_task(voice_thread(websocket))

    async def recv_loop():
        try:
            async for msg in websocket:
                if isinstance(msg, str):
                    if msg.startswith("CMD:SET_FPS:"):
                        target_fps = float(msg.split(":")[-1])
                        _PI_STATE["sleep_time"] = 1.0 / max(1.0, target_fps)
                    elif msg.startswith("CMD:SYNC_POLICY:"):
                        policy_str = msg.replace("CMD:SYNC_POLICY:", "")
                        payload = json.loads(policy_str)
                        _PI_STATE["policies"] = payload.get("event_policies", [])
                        if "storage_budget_mb_per_hour" in payload:
                            _PI_STATE["storage_budget_mb_per_hour"] = float(payload.get("storage_budget_mb_per_hour", 500.0))
                        console_info(f"加载了 {len(_PI_STATE['policies'])} 条裁剪策略")
                    elif msg.startswith("CMD:TTS:"):
                        tts_text = msg.replace("CMD:TTS:", "")
                        console_info(f"[专家结论] {tts_text}")
                        if _PI_STATE["has_speaker"] and tts_queue is not None:
                            await tts_queue.put(tts_text)
                    elif msg.startswith("CMD:EXPERT_RESULT:"):
                        result_raw = msg.replace("CMD:EXPERT_RESULT:", "", 1)
                        payload = json.loads(result_raw)
                        event_id = str(payload.get("event_id") or uuid.uuid4())
                        text = payload.get("text", "")
                        should_speak = bool(payload.get("speak", False))
                        severity = payload.get("severity", "info")
                        _PI_STATE["expert_results"][event_id] = {
                            "text": text,
                            "severity": severity,
                            "received_at": time.time()
                        }
                        if text:
                            console_info(f"[专家研判-{severity}] ({event_id}) {text}")
                            if should_speak and _PI_STATE["has_speaker"] and tts_queue is not None:
                                await tts_queue.put(text)

                        ack = {
                            "event_id": event_id,
                            "received": True,
                            "spoken": bool(should_speak and _PI_STATE["has_speaker"]),
                            "timestamp": time.time(),
                        }
                        await websocket.send(f"PI_EXPERT_ACK:{json.dumps(ack, ensure_ascii=False)}")
                    # 👇 新增拦截PC大模型结果的逻辑
                    elif msg.startswith("监控指令:"):
                        res_text = msg.replace("监控指令:", "").strip()
                        console_info(f"大模型看懂了: {res_text}")
        except Exception as e:
            console_error(f"指令接收中断: {e}")

    async def send_loop():
        # 换用原生的 YOLO Detector
        from edge_vision.yolo_detector import GeneralYoloDetector
        yolo_detector = GeneralYoloDetector()

        try:
            while running:
                target_sleep = max(0.03, float(_PI_STATE.get("sleep_time", 0.2)))
                await asyncio.sleep(target_sleep)

                frame = await get_frame()
                if frame is not None:
                    flipped = cv2.flip(frame, 0)
                    metrics = capture_controller.evaluate_frame(flipped)
                    profile = capture_controller.suggest_profile(
                        metrics,
                        storage_budget_mb_per_hour=float(_PI_STATE.get("storage_budget_mb_per_hour", 500.0)),
                    )

                    # 动态收敛至建议fps，同时保留PC下发上限能力
                    _PI_STATE["sleep_time"] = max(_PI_STATE["sleep_time"], 1.0 / max(1.0, profile.fps))
                    encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), int(profile.preview_jpeg_quality)]
                    hd_encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), int(profile.event_jpeg_quality)]

                    triggered_events = yolo_detector.process_frame(flipped, _PI_STATE["policies"])
                    for event_name, event_frame, detected_str in triggered_events:
                        ret, buf = cv2.imencode('.jpg', event_frame, hd_encode_param)
                        if ret:
                            b64_img = base64.b64encode(buf.tobytes()).decode('utf-8')
                            payload = {
                                "event_id": str(uuid.uuid4()),
                                "event_name": event_name,
                                "detected_classes": detected_str,
                                "timestamp": time.time(),
                                "capture_metrics": metrics,
                            }
                            await websocket.send(f"PI_EXPERT_EVENT:{json.dumps(payload, ensure_ascii=False)}:{b64_img}")
                            console_info(f"捕捉违规，上传关键帧 [{event_name}] classes={detected_str}")

                    if len(_PI_STATE["expert_results"]) > 200:
                        oldest = sorted(_PI_STATE["expert_results"].items(), key=lambda kv: kv[1].get("received_at", 0))[:80]
                        for key, _ in oldest:
                            _PI_STATE["expert_results"].pop(key, None)

                    resized = cv2.resize(flipped, (int(profile.preview_width), int(profile.preview_height)))
                    ret, buf = cv2.imencode('.jpg', resized, encode_param)
                    if ret:
                        await websocket.send(buf.tobytes())
        except Exception as e:
            console_error(f"视频流发送异常: {e}")

    done, pending = await asyncio.wait(
        [asyncio.create_task(recv_loop()), asyncio.create_task(send_loop())],
        return_when=asyncio.FIRST_COMPLETED
    )
    for t in pending: t.cancel()
    console_info("[INFO] 客户端连接已关闭")


async def main_async():
    global picam2, tts_queue, running
    NetworkDiscoveryResponder().start()

    if PICAMERA_AVAILABLE:
        try:
            picam2 = Picamera2()
            config = picam2.create_video_configuration(main={"size": (1280, 720), "format": "RGB888"})
            picam2.configure(config)
            picam2.start()
            console_info("Picamera2 硬件初始化成功")
        except Exception as e:
            console_error(f"摄像头启动失败: {e}")

    _PI_STATE["has_mic"], _PI_STATE["has_speaker"] = detect_audio_capabilities()

    if _PI_STATE["has_speaker"] and init_tts():
        tts_queue = asyncio.Queue()

        async def _tts_worker():
            while running:
                txt = await tts_queue.get()
                speak_async(txt)

        asyncio.create_task(_tts_worker())

    async with websockets.serve(handle_client, "0.0.0.0", 8001, ping_interval=20, ping_timeout=20, max_size=None):
        console_info(f"WebSocket服务已就绪 ws://{get_local_ip()}:8001")
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
    """独立的语音采集与识别协程（防崩溃容错版）"""
    try:
        # 1. 尝试初始化模型和硬件
        model_dir = os.path.join(os.path.dirname(__file__), "voice", "model")
        recognizer = PiVoiceRecognizer(model_dir)
        interaction = PiVoiceInteraction(recognizer)

        # 开启麦克风
        p = pyaudio.PyAudio()
        stream = p.open(format=pyaudio.paInt16, channels=1, rate=16000,
                        input=True, frames_per_buffer=4000)
        stream.start_stream()

        console_info("🎤 Pi端本地语音引擎已就绪")

    except Exception as e:
        # ★ 核心拦截：如果没插麦克风，在这里捕获报错，安全退出
        console_info(f"未检测到有效麦克风硬件，已自动跳过语音唤醒功能。")
        return  # 直接 `return` 结束该协程，主程序依然会完美运行！

    # 2. 正常的工作循环（只有硬件成功才会走到这里）
    while running:
        try:
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

                # 回传给 PC
                await websocket.send(f"PI_VOICE_COMMAND:{cmd_text}")
                interaction.is_active = False  # 完成一次指令后回到待机
        except Exception as e:
            break

    # 3. 安全清理资源
    try:
        stream.stop_stream()
        stream.close()
        p.terminate()
    except:
        pass


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
        print("[INFO] 核心通信与语音依赖包已就绪.")
    except ImportError as e:
        print(f"[ERROR] 缺少依赖: {e}")
        print("[INFO] 请先运行: pip install -e .")
        sys.exit(1)

    # ---------------------------------------------------------
    # [2/3] 摄像头硬件自检
    # ---------------------------------------------------------
    print("\n[INFO] [2/3] 检查摄像头硬件...")
    if PICAMERA_AVAILABLE:
        print("[INFO] Picamera2 模块加载成功，原生摄像头就绪.")
    else:
        print("[WARN] Picamera2 不可用，将尝试使用 OpenCV 备用捕捉模块.")

    # ---------------------------------------------------------
    # [3/4] 音频硬件能力自检
    # ---------------------------------------------------------
    print("\n[INFO] [3/4] 检查音频硬件能力...")
    has_mic, has_speaker = detect_audio_capabilities()
    print(f"[INFO] 麦克风: {'可用' if has_mic else '不可用'} | 扬声器: {'可用' if has_speaker else '不可用'}")

    # ---------------------------------------------------------
    # [4/4] 离线语音唤醒模型自检
    # ---------------------------------------------------------
    print("\n[INFO] [4/4] 检查 Vosk 离线唤醒模型...")
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