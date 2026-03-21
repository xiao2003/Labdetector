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

import base64
import importlib
import importlib.util
from typing import List, Optional, Tuple

try:
    from .config import get_pi_config
    from .tools.version_manager import get_app_version
except ImportError:
    from config import get_pi_config
    from tools.version_manager import get_app_version
APP_VERSION = get_app_version()

cv2 = None
websockets = None
pyaudio = None
AdaptiveCaptureController = None
PiVoiceInteraction = None
PiVoiceRecognizer = None
check_and_download_vosk = None

try:
    from picamera2 import Picamera2

    PICAMERA_AVAILABLE = True
except ImportError:
    PICAMERA_AVAILABLE = False

PI_CORE_DEPENDENCY_MAP = {
    "numpy": "numpy",
    "cv2": "opencv-python-headless",
    "websockets": "websockets",
}

PI_OPTIONAL_DEPENDENCY_MAP = {
    "pyaudio": "pyaudio",
    "vosk": "vosk",
    "pyttsx3": "pyttsx3",
}

PI_DEPENDENCY_MAP = {
    **PI_CORE_DEPENDENCY_MAP,
    **PI_OPTIONAL_DEPENDENCY_MAP,
}

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


def _find_missing_pi_dependencies(module_map: Optional[dict] = None) -> List[str]:
    target_map = module_map or PI_DEPENDENCY_MAP
    missing: List[str] = []
    for module_name, package_name in target_map.items():
        if importlib.util.find_spec(module_name) is None:
            missing.append(package_name)
    return sorted(set(missing))


def _ensure_pi_pip_available() -> Tuple[bool, List[str]]:
    logs: List[str] = []
    check_cmd = [sys.executable, "-m", "pip", "--version"]
    check = subprocess.run(check_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if check.returncode == 0:
        text = check.stdout.decode("utf-8", errors="ignore").strip()
        if text:
            logs.append(f"[INFO] pip 已就绪: {text}")
        return True, logs

    logs.append("[WARN] pip 不可用，尝试 ensurepip 自动补齐。")
    ensure = subprocess.run([sys.executable, "-m", "ensurepip", "--upgrade"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = ensure.stdout.decode("utf-8", errors="ignore").strip()
    if out:
        logs.extend([f"[INFO] {line}" for line in out.splitlines()[-12:]])

    recheck = subprocess.run(check_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if recheck.returncode == 0:
        text = recheck.stdout.decode("utf-8", errors="ignore").strip()
        if text:
            logs.append(f"[INFO] pip 修复成功: {text}")
        return True, logs

    logs.append("[ERROR] pip 仍不可用，无法自动安装依赖。")
    return False, logs


def _install_pi_dependencies(packages: List[str]) -> Tuple[List[str], List[str], List[str]]:
    logs: List[str] = []
    required = sorted(set(packages))
    if not required:
        return [], [], ["[INFO] Pi 端无缺失依赖，无需安装。"]

    pip_ok, pip_logs = _ensure_pi_pip_available()
    logs.extend(pip_logs)
    if not pip_ok:
        return [], required, logs

    installed: List[str] = []
    failed: List[str] = []
    for package_name in required:
        cmd = [sys.executable, "-m", "pip", "install", package_name]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        output = proc.stdout.decode("utf-8", errors="ignore")
        tail_lines = [line for line in output.splitlines() if line.strip()][-10:]
        if proc.returncode == 0:
            installed.append(package_name)
            logs.append(f"[INFO] 安装成功: {package_name}")
        else:
            failed.append(package_name)
            logs.append(f"[ERROR] 安装失败: {package_name}")
        logs.extend([f"[INFO] {line}" for line in tail_lines])

    return installed, failed, logs


def _import_first_module(*module_names: str):
    last_error: Optional[Exception] = None
    for module_name in module_names:
        try:
            return importlib.import_module(module_name)
        except Exception as exc:
            last_error = exc
    if last_error is not None:
        raise last_error
    raise ImportError("未提供可导入模块名")


def _load_runtime_modules() -> None:
    global cv2, websockets, pyaudio
    global AdaptiveCaptureController, PiVoiceInteraction, PiVoiceRecognizer, check_and_download_vosk

    if cv2 is None:
        cv2 = importlib.import_module("cv2")
    if websockets is None:
        websockets = importlib.import_module("websockets")
    if AdaptiveCaptureController is None:
        module = _import_first_module("edge_vision.adaptive_capture", "pi.edge_vision.adaptive_capture")
        AdaptiveCaptureController = getattr(module, "AdaptiveCaptureController")

    if pyaudio is None:
        try:
            pyaudio = importlib.import_module("pyaudio")
        except Exception:
            pyaudio = None

    if PiVoiceInteraction is None:
        try:
            module = _import_first_module("voice.interaction", "pi.voice.interaction")
            PiVoiceInteraction = getattr(module, "PiVoiceInteraction")
        except Exception:
            PiVoiceInteraction = None

    if PiVoiceRecognizer is None:
        try:
            module = _import_first_module("voice.recognizer", "pi.voice.recognizer")
            PiVoiceRecognizer = getattr(module, "PiVoiceRecognizer")
        except Exception:
            PiVoiceRecognizer = None

    if check_and_download_vosk is None:
        try:
            module = _import_first_module("tools.model_downloader", "pi.tools.model_downloader")
            check_and_download_vosk = getattr(module, "check_and_download_vosk")
        except Exception:
            check_and_download_vosk = None

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
    global pyaudio
    has_mic, has_speaker = False, False
    if pyaudio is None:
        try:
            pyaudio = importlib.import_module("pyaudio")
        except Exception:
            return has_mic, has_speaker
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
                        console_info(f"已同步策略 {len(_PI_STATE['policies'])} 条。")
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
        try:
            yolo_module = _import_first_module("edge_vision.yolo_detector", "pi.edge_vision.yolo_detector")
            GeneralYoloDetector = getattr(yolo_module, "GeneralYoloDetector")
        except Exception as exc:
            console_error(f"YOLO 检测器加载失败: {exc}")
            return
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
                    for event_name, event_frame, detected_str, policy_meta in triggered_events:
                        ret, buf = cv2.imencode('.jpg', event_frame, hd_encode_param)
                        if ret:
                            b64_img = base64.b64encode(buf.tobytes()).decode('utf-8')
                            payload = {
                                "event_id": str(uuid.uuid4()),
                                "event_name": event_name,
                                "expert_code": str((policy_meta or {}).get("expert_code", "") or ""),
                                "policy_name": str((policy_meta or {}).get("policy_name", event_name) or event_name),
                                "policy_action": str((policy_meta or {}).get("policy_action", "") or ""),
                                "detected_classes": detected_str,
                                "timestamp": time.time(),
                                "capture_metrics": {
                                    **metrics,
                                    "expert_code": str((policy_meta or {}).get("expert_code", "") or ""),
                                    "policy_name": str((policy_meta or {}).get("policy_name", event_name) or event_name),
                                    "policy_action": str((policy_meta or {}).get("policy_action", "") or ""),
                                },
                            }
                            await websocket.send(f"PI_EXPERT_EVENT:{json.dumps(payload, ensure_ascii=False)}:{b64_img}")
                            console_info(
                                f"捕捉违规，上传关键帧 [{event_name}] expert={payload['expert_code'] or 'unknown'} classes={detected_str}"
                            )

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

    try:
        _load_runtime_modules()
    except Exception as exc:
        console_error(f"运行时依赖未就绪: {exc}")
        return

    try:
        if check_and_download_vosk is not None:
            check_and_download_vosk()
    except Exception as exc:
        console_info(f"[WARN] 离线语音模型检查失败: {exc}")

    NetworkDiscoveryResponder().start()

    if PICAMERA_AVAILABLE:
        try:
            picam2 = Picamera2()
            config = picam2.create_video_configuration(main={"size": (1280, 720), "format": "RGB888"})
            picam2.configure(config)
            picam2.start()
            console_info("Picamera2 硬件初始化成功。")
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
        console_info(f"WebSocket 服务已就绪: ws://{get_local_ip()}:8001")
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
    """独立的语音采集与识别协程，麦克风不可用时自动跳过。"""
    try:
        model_dir = os.path.join(os.path.dirname(__file__), "voice", "model")
        recognizer = PiVoiceRecognizer(model_dir)
        interaction = PiVoiceInteraction(recognizer)

        p = pyaudio.PyAudio()
        stream = p.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=16000,
            input=True,
            frames_per_buffer=4000,
        )
        stream.start_stream()
        console_info("Pi 端本地语音引擎已就绪。")
    except Exception:
        console_info("未检测到有效麦克风设备，已跳过语音唤醒功能。")
        return

    while running:
        try:
            data = await asyncio.to_thread(stream.read, 4000, exception_on_overflow=False)
            event = interaction.process_audio(data)
            if event == "EVENT:WOKEN":
                speak_async("我在。")
                await websocket.send("PI_EVENT:WOKEN")
            elif event and event.startswith("CMD_TEXT:"):
                cmd_text = event.replace("CMD_TEXT:", "")
                console_info(f"语音识别指令: {cmd_text}")
                await websocket.send(f"PI_VOICE_COMMAND:{cmd_text}")
                interaction.is_active = False
        except Exception:
            break

    try:
        stream.stop_stream()
        stream.close()
        p.terminate()
    except Exception:
        pass


def run_pi_self_check(auto_install: Optional[bool] = None) -> bool:
    """执行 Pi 边缘节点自检，必要时自动安装依赖。"""
    if auto_install is None:
        auto_install = bool(get_pi_config("self_check.auto_install_dependencies", True))

    print("\n" + "=" * 55)
    print(f"[INFO] NeuroLab Hub V{APP_VERSION} (Pi 边缘端) - 节点自检")
    print("=" * 55)

    print("\n[INFO] [1/3] 检查 Python 依赖环境...")
    missing_core = _find_missing_pi_dependencies(PI_CORE_DEPENDENCY_MAP)
    missing_optional = _find_missing_pi_dependencies(PI_OPTIONAL_DEPENDENCY_MAP)
    missing_all = sorted(set(missing_core + missing_optional))
    if not missing_all:
        print("[INFO] 依赖检查通过。")
    else:
        if missing_core:
            print(f"[WARN] 核心依赖缺失: {', '.join(missing_core)}")
        if missing_optional:
            print(f"[WARN] 可选依赖缺失: {', '.join(missing_optional)}")

        if auto_install:
            print("[INFO] 自动安装已开启，尝试补齐依赖...")
            _, _, logs = _install_pi_dependencies(missing_all)
            for line in logs:
                print(line)
            missing_core = _find_missing_pi_dependencies(PI_CORE_DEPENDENCY_MAP)
            missing_optional = _find_missing_pi_dependencies(PI_OPTIONAL_DEPENDENCY_MAP)
            if not missing_core and not missing_optional:
                print("[INFO] 缺失依赖已自动安装完成。")
        else:
            print("[WARN] 自动安装未开启，请手动安装后重试。")

    print("\n[INFO] [2/3] 检查摄像头与音频硬件...")
    if PICAMERA_AVAILABLE:
        print("[INFO] 检测到 Picamera2 驱动。")
    else:
        print("[WARN] 未检测到 Picamera2，将使用兼容模式或等待外部视频源。")
    has_mic, has_speaker = detect_audio_capabilities()
    print(f"[INFO] 麦克风: {'可用' if has_mic else '不可用'}，扬声器: {'可用' if has_speaker else '不可用'}")

    print("\n[INFO] [3/3] 检查语音模型资产...")
    vosk_ready = False
    try:
        _load_runtime_modules()
        if check_and_download_vosk is not None:
            check_and_download_vosk()
            vosk_ready = True
            print("[INFO] 离线语音模型检查完成。")
        else:
            print("[WARN] 未找到语音模型下载模块，跳过该项。")
    except Exception as exc:
        print(f"[WARN] 离线语音模型检查失败: {exc}")

    overall_ok = not missing_core
    print("\n" + "=" * 55)
    if overall_ok:
        if missing_optional:
            print(f"[WARN] Pi 自检通过，但仍有可选依赖未安装: {', '.join(missing_optional)}")
        elif vosk_ready:
            print("[INFO] Pi 边缘节点自检通过，可以直接启动。")
        else:
            print("[WARN] Pi 自检通过（核心依赖与硬件正常），语音模型可稍后补齐。")
    else:
        print(f"[ERROR] Pi 自检失败，仍缺失核心依赖: {', '.join(missing_core)}")
    print("=" * 55 + "\n")
    return overall_ok


if __name__ == '__main__':
    check_ok = run_pi_self_check()
    if not check_ok:
        sys.exit(2)

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
