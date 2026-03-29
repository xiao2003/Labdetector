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
    from .config import get_pi_config, get_pi_path_config
    from .tools.version_manager import get_app_version
except ImportError:
    from config import get_pi_config, get_pi_path_config
    from tools.version_manager import get_app_version
APP_VERSION = get_app_version()

def _get_voice_model_dir() -> str:
    return get_pi_path_config("voice.model_path", "voice/model")


def _get_wake_aliases() -> list[str]:
    raw_value = str(get_pi_config("voice.wake_aliases", "") or "").strip()
    if not raw_value:
        return ["小爱同学", "小爱同", "小爱", "小艾同学", "晓爱同学", "哎同学", "爱同学"]
    return [item.strip() for item in raw_value.split(",") if item.strip()]


def _get_ws_port() -> int:
    try:
        port = int(get_pi_config("network.ws_port", 8001) or 8001)
    except Exception:
        return 8001
    return port if 1 <= port <= 65535 else 8001

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
    "torch": "torch",
    "torchvision": "torchvision",
    "ultralytics": "ultralytics",
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
    "sleep_time": 0.2,  # 默认先以 5fps 稳定档启动，避免 Pi 5 首轮初始化抖动过大
    "policies": [],  # 新增：缓存策略
    "has_mic": False,
    "has_speaker": False,
    "wake_word": str(get_pi_config("voice.wake_word", "小爱同学") or "小爱同学"),
    "wake_aliases": _get_wake_aliases(),
    "expert_results": {},
    "storage_budget_mb_per_hour": 400.0
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
_TTS_PROCESS = None
_TTS_LOCK = threading.Lock()


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


def stop_tts_playback():
    global _TTS_PROCESS
    try:
        with _TTS_LOCK:
            if _TTS_PROCESS is not None:
                try:
                    _TTS_PROCESS.terminate()
                except Exception:
                    pass
                _TTS_PROCESS = None
            if _TTS_ENGINE not in (None, "espeak") and hasattr(_TTS_ENGINE, "stop"):
                _TTS_ENGINE.stop()
    except Exception:
        pass

    if tts_queue is not None:
        try:
            while True:
                tts_queue.get_nowait()
                tts_queue.task_done()
        except asyncio.QueueEmpty:
            pass


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
        global _TTS_PROCESS
        if not t or not _TTS_ENGINE: return
        try:
            with _TTS_LOCK:
                if _TTS_ENGINE == "espeak":
                    cmd = shutil.which("espeak")
                    if cmd:
                        _TTS_PROCESS = subprocess.Popen([str(cmd), "-v", "zh", t], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        _TTS_PROCESS.wait()
                        _TTS_PROCESS = None
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
        self.ws_port = _get_ws_port()

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
                            resp = json.dumps({'type': 'raspberry_pi_response', 'ip': self.local_ip, 'ws_port': self.ws_port})
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
    loop = asyncio.get_running_loop()

    def _schedule_progress(payload: dict) -> None:
        try:
            message = f"PI_PROGRESS:{json.dumps(payload, ensure_ascii=False)}"
            asyncio.run_coroutine_threadsafe(websocket.send(message), loop)
        except Exception:
            pass

    async def recv_loop():
        try:
            async for msg in websocket:
                if isinstance(msg, str):
                    if msg.startswith("CMD:SET_FPS:"):
                        target_fps = float(msg.split(":")[-1])
                        _PI_STATE["sleep_time"] = 1.0 / max(1.0, target_fps)
                    elif msg.startswith("CMD:SYNC_CONFIG:"):
                        config_str = msg.replace("CMD:SYNC_CONFIG:", "", 1)
                        try:
                            payload = json.loads(config_str)
                        except Exception:
                            payload = {}
                        wake_word = str(payload.get("wake_word", "") or "").strip()
                        wake_aliases_raw = payload.get("wake_aliases", [])
                        if isinstance(wake_aliases_raw, str):
                            wake_aliases = [item.strip() for item in wake_aliases_raw.split(",") if item.strip()]
                        elif isinstance(wake_aliases_raw, list):
                            wake_aliases = [str(item).strip() for item in wake_aliases_raw if str(item).strip()]
                        else:
                            wake_aliases = []
                        if wake_word:
                            _PI_STATE["wake_word"] = wake_word
                            console_info(f"已同步 Pi 唤醒词: {wake_word}")
                        _PI_STATE["wake_aliases"] = wake_aliases
                        if wake_aliases:
                            console_info(f"已同步 Pi 唤醒别名 {len(wake_aliases)} 项")
                    elif msg.startswith("CMD:SYNC_POLICY:"):
                        policy_str = msg.replace("CMD:SYNC_POLICY:", "")
                        payload = json.loads(policy_str)
                        _PI_STATE["policies"] = payload.get("event_policies", [])
                        if "storage_budget_mb_per_hour" in payload:
                            _PI_STATE["storage_budget_mb_per_hour"] = float(payload.get("storage_budget_mb_per_hour", 400.0))
                        console_info(f"已同步策略 {len(_PI_STATE['policies'])} 条。")
                    elif msg.startswith("CMD:RUN_SELF_CHECK"):
                        console_info("收到 PC 发起的远程自检请求。")

                        def _worker() -> None:
                            run_pi_self_check(progress_callback=_schedule_progress)

                        threading.Thread(target=_worker, daemon=True, name="PiRemoteSelfCheck").start()
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
                        storage_budget_mb_per_hour=float(_PI_STATE.get("storage_budget_mb_per_hour", 400.0)),
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
            check_and_download_vosk(_get_voice_model_dir())
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

    ws_port = _get_ws_port()
    async with websockets.serve(handle_client, "0.0.0.0", ws_port, ping_interval=20, ping_timeout=20, max_size=None):
        console_info(f"WebSocket 服务已就绪: ws://{get_local_ip()}:{ws_port}")
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
        model_dir = _get_voice_model_dir()
        recognizer = PiVoiceRecognizer(model_dir)
        interaction = PiVoiceInteraction(
            recognizer,
            wake_word=str(_PI_STATE.get("wake_word") or "小爱同学"),
            wake_aliases=_PI_STATE.get("wake_aliases") or [],
        )

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
            synced_wake_word = str(_PI_STATE.get("wake_word") or "").strip()
            if synced_wake_word and interaction.wake_word != synced_wake_word:
                interaction.wake_word = synced_wake_word
            synced_aliases = _PI_STATE.get("wake_aliases") or []
            if interaction.wake_aliases != synced_aliases:
                interaction.wake_aliases = [str(item).strip() for item in synced_aliases if str(item).strip()]
            event = interaction.process_audio(data)
            if event == "EVENT:WOKEN":
                stop_tts_playback()
                speak_async("我在。")
                await websocket.send("PI_EVENT:WOKEN")
            elif event == "EVENT:STOP_TTS":
                console_info("已收到本地停止播报指令")
                stop_tts_playback()
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


def _emit_pi_progress(
    progress_callback,
    *,
    source: str,
    stage: str,
    title: str,
    detail: str,
    current: int,
    total: int,
    percent: float,
    status: str = "running",
    missing_before: Optional[List[str]] = None,
    installed: Optional[List[str]] = None,
    remaining_failures: Optional[List[str]] = None,
) -> None:
    if progress_callback is None:
        return
    payload = {
        "node_id": "local",
        "source": source,
        "stage": stage,
        "title": title,
        "detail": detail,
        "current": int(current),
        "total": int(total),
        "percent": max(0.0, min(100.0, float(percent))),
        "status": status,
        "missing_before": list(missing_before or []),
        "installed": list(installed or []),
        "remaining_failures": list(remaining_failures or []),
    }
    progress_callback(payload)


def run_pi_self_check(auto_install: Optional[bool] = None, progress_callback=None) -> bool:
    """执行 Pi 边缘节点自检，必要时自动安装依赖。"""
    if auto_install is None:
        auto_install = bool(get_pi_config("self_check.auto_install_dependencies", True))

    total_steps = 3
    installed_packages: List[str] = []
    missing_before: List[str] = []
    remaining_failures: List[str] = []

    print("\n" + "=" * 55)
    print(f"[INFO] NeuroLab Hub V{APP_VERSION} (Pi 边缘端) - 节点自检")
    print("=" * 55)

    _emit_pi_progress(
        progress_callback,
        source="self_check",
        stage="scan",
        title="扫描依赖与硬件",
        detail="正在检查 Python 依赖、摄像头与语音模型资产",
        current=0,
        total=total_steps,
        percent=8.0,
    )
    print("\n[INFO] [1/3] 检查 Python 依赖环境...")
    missing_core = _find_missing_pi_dependencies(PI_CORE_DEPENDENCY_MAP)
    missing_optional = _find_missing_pi_dependencies(PI_OPTIONAL_DEPENDENCY_MAP)
    missing_all = sorted(set(missing_core + missing_optional))
    missing_before = list(missing_all)
    if not missing_all:
        print("[INFO] 依赖检查通过。")
    else:
        if missing_core:
            print(f"[WARN] 核心依赖缺失: {', '.join(missing_core)}")
        if missing_optional:
            print(f"[WARN] 可选依赖缺失: {', '.join(missing_optional)}")

        if auto_install:
            print("[INFO] 自动安装已开启，尝试补齐依赖...")
            _emit_pi_progress(
                progress_callback,
                source="self_check",
                stage="repair",
                title="自动补全依赖",
                detail=f"正在补齐 {len(missing_all)} 项缺失依赖",
                current=1,
                total=total_steps,
                percent=30.0,
                missing_before=missing_all,
            )
            installed_packages, failed_packages, logs = _install_pi_dependencies(missing_all)
            for line in logs:
                print(line)
            missing_core = _find_missing_pi_dependencies(PI_CORE_DEPENDENCY_MAP)
            missing_optional = _find_missing_pi_dependencies(PI_OPTIONAL_DEPENDENCY_MAP)
            remaining_failures = list(sorted(set(missing_core + missing_optional + failed_packages)))
            if not missing_core and not missing_optional:
                print("[INFO] 缺失依赖已自动安装完成。")
        else:
            print("[WARN] 自动安装未开启，请手动安装后重试。")
            remaining_failures = list(missing_all)

    _emit_pi_progress(
        progress_callback,
        source="self_check",
        stage="recheck",
        title="再次自检",
        detail="正在重新检查依赖、硬件和语音模型资产",
        current=1,
        total=total_steps,
        percent=58.0,
        missing_before=missing_before,
        installed=installed_packages,
        remaining_failures=remaining_failures,
    )

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
            check_and_download_vosk(_get_voice_model_dir())
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
    remaining_failures = list(sorted(set(missing_core + missing_optional)))
    _emit_pi_progress(
        progress_callback,
        source="self_check",
        stage="done",
        title="Pi 边缘端自检",
        detail="Pi 自检通过，可以继续运行。" if overall_ok else "Pi 自检仍存在缺失项，请先处理。",
        current=total_steps,
        total=total_steps,
        percent=100.0,
        status="success" if overall_ok else "error",
        missing_before=missing_before,
        installed=installed_packages,
        remaining_failures=remaining_failures,
    )
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
