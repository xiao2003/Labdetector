#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import asyncio
import websockets
import cv2
import numpy as np
import threading
import subprocess
import ctypes
import base64
import requests
import win32com.client
import sys
import os
import time
from typing import Optional

# ====================== 全局配置 ======================
CONFIG = {
    "camera": {"index": 0, "resolution": (1280, 720)},
    "ollama": {"host": "http://localhost:11434", "default_models": [
        "llava:7b-v1.5-q4_K_M",  # 轻量模型（约4.5GB）
        "llava:13b-v1.5-q4_K_M",  # 大模型（约10GB）
        "llava:34b-v1.5-q4_K_M",  # 超大模型（约20GB）
        "llava:latest"  # 最新版模型
    ]},
    "inference": {"interval": 5, "timeout": 20},
    "gpu": {"layers": 35},
    "websocket": {"host": "192.168.31.31", "port": 8001},  # 树莓派WS地址
    "display": {"width": 1920, "height": 1080},
    "ws_retry": {"max_attempts": 5, "interval": 3}  # WS重试配置：最多5次，间隔3秒
}
# 全局状态
_STATE = {
    "running": True,
    "mode": "",  # camera / websocket
    "frame_buffer": np.zeros((CONFIG["camera"]["resolution"][1], CONFIG["camera"]["resolution"][0], 3), np.uint8),
    "tts_speaker": None,
    "selected_model": "",
    "ai_backend": "",  # "ollama" or "qwen"
    "ws_connected": False,
    "ws_loop": None,
    "ws_task": None,
    "ws_retry_attempts": 0,  # WS重试次数
    "voice_interaction": None,  # 语音交互实例
    "voice_interaction_enabled": False  # 语音交互是否启用
}


# ====================== 依赖检查 & Ollama管理 ======================
def check_dependencies():
    """检查并自动安装所有依赖包"""
    required_packages = ["cv2", "numpy", "requests", "win32com.client", "websockets", "speech_recognition", "pyaudio"]
    missing_pkgs = []
    for pkg in required_packages:
        try:
            __import__(pkg.split(".")[0])
        except ImportError:
            missing_pkgs.append(pkg.split(".")[0])
    if missing_pkgs:
        print(f"[ERROR] 缺失依赖包: {', '.join(missing_pkgs)}")
        print("[INFO] 正在自动安装依赖...")
        try:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "-U"] + missing_pkgs,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            print("[INFO] 依赖包安装成功")
        except Exception as e:
            print(f"[ERROR] 依赖安装失败: {str(e)[:50]}")
            return False

    ollama_exe = "ollama.exe"
    default_path = "C:\\Users\\Administrator\\AppData\\Local\\Programs\\Ollama\\ollama.exe"
    if os.path.exists(default_path):
        ollama_exe = default_path
    if not os.path.exists(ollama_exe) and not subprocess.run("where ollama >NUL 2>&1", shell=True).returncode == 0:
        print("[ERROR] 未检测到Ollama，请先安装Ollama（https://ollama.com/download/windows）")
        return False
    return True


def list_ollama_models():
    """获取本地已安装的Ollama模型列表"""
    try:
        ollama_exe = "ollama.exe"
        default_path = "C:\\Users\\Administrator\\AppData\\Local\\Programs\\Ollama\\ollama.exe"
        if os.path.exists(default_path):
            ollama_exe = default_path
        subprocess.Popen(
            [ollama_exe, "serve"],
            creationflags=subprocess.CREATE_NEW_CONSOLE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        time.sleep(3)
        resp = requests.get(f"{CONFIG['ollama']['host']}/api/tags", timeout=5)
        if resp.status_code == 200:
            local_models = [m.get("name") for m in resp.json().get("models", []) if "llava" in m.get("name", "")]
            subprocess.run('taskkill /f /im ollama.exe >NUL 2>&1', shell=True)
            time.sleep(0.5)
            return local_models
    except:
        pass
    return []


def select_ai_backend():
    """选择AI后端：Ollama或Qwen"""
    print("\n===== AI后端选择 =====")
    print("1. Ollama (本地模型，如LLaVA)")
    print("2. Qwen3.5-Plus (云端模型，需API密钥)")
    while True:
        try:
            choice = input("\n请选择AI后端 (1 或 2): ").strip()
            if not choice.isdigit():
                print("请输入有效的数字")
                continue
            choice_idx = int(choice)
            if choice_idx == 1:
                _STATE["ai_backend"] = "ollama"
                print("\n[INFO] 已选择Ollama后端")
                break
            elif choice_idx == 2:
                _STATE["ai_backend"] = "qwen"
                print("\n[INFO] 已选择Qwen3.5-Plus后端")
                break
            else:
                print("请输入1或2")
        except:
            print("输入无效，请重新选择")
    return True


def select_model():
    """命令行交互选择模型（仅当使用Ollama时）"""
    if _STATE["ai_backend"] == "qwen":
        # 如果选择了Qwen，则不需要选择具体模型
        _STATE["selected_model"] = "qwen-vl-max"
        print("[INFO] 已选择Qwen-VL-Max模型")
        return True

    print("\n===== 模型选择 =====")
    local_models = list_ollama_models()
    all_models = list(set(CONFIG["ollama"]["default_models"] + local_models))
    all_models.sort()
    print("可用模型列表（输入序号选择）：")
    for idx, model in enumerate(all_models, 1):
        status = "[已安装]" if model in local_models else "[未安装，将自动拉取]"
        print(f"{idx}. {model} {status}")
    print(f"{len(all_models) + 1}. 自定义模型")

    while True:
        try:
            choice = input("\n请输入模型序号: ").strip()
            if not choice.isdigit():
                print("请输入有效的数字序号")
                continue
            choice_idx = int(choice)
            if 1 <= choice_idx <= len(all_models):
                _STATE["selected_model"] = all_models[choice_idx - 1]
                break
            elif choice_idx == len(all_models) + 1:
                custom_model = input("请输入自定义模型名称（如llava:7b）: ").strip()
                if custom_model:
                    _STATE["selected_model"] = custom_model
                    break
                else:
                    print("模型名称不能为空")
            else:
                print(f"请输入1-{len(all_models) + 1}之间的数字")
        except:
            print("输入无效，请重新选择")

    print(f"\n[INFO] 已选择模型: {_STATE['selected_model']}")
    return True


def pull_ollama_model():
    """自动拉取选中的模型（不存在时，仅当使用Ollama时）"""
    if _STATE["ai_backend"] == "qwen":
        # 如果使用Qwen，则跳过Ollama模型拉取
        print("[INFO] 使用Qwen后端，跳过Ollama模型拉取")
        return True

    model = _STATE["selected_model"]
    if not model:
        print("[ERROR] 未选择模型")
        return False

    local_models = list_ollama_models()
    if model in local_models:
        print(f"[INFO] 模型 {model} 已存在，无需拉取")
        return True

    subprocess.run('taskkill /f /im ollama.exe >NUL 2>&1', shell=True)
    time.sleep(0.5)
    print(f"\n[INFO] 开始拉取模型 {model}")
    print("=" * 50)

    ollama_exe = "ollama.exe"
    default_path = "C:\\Users\\Administrator\\AppData\\Local\\Programs\\Ollama\\ollama.exe"
    if os.path.exists(default_path):
        ollama_exe = default_path

    try:
        pull_proc = subprocess.Popen(
            [ollama_exe, "pull", model],
            shell=True,
            stdout=sys.stdout,
            stderr=sys.stderr,
            creationflags=subprocess.CREATE_NEW_CONSOLE if os.name == 'nt' else 0
        )
        pull_proc.wait(timeout=3600)
        if pull_proc.returncode == 0:
            print("=" * 50)
            print(f"[INFO] 模型 {model} 拉取成功")
            return True
        else:
            print("=" * 50)
            print(f"[ERROR] 模型 {model} 拉取失败")
            return False
    except subprocess.TimeoutExpired:
        print("=" * 50)
        print("[ERROR] 模型拉取超时（超过1小时）")
        return False
    except Exception as e:
        print("=" * 50)
        print(f"[ERROR] 模型拉取异常: {str(e)[:50]}")
        return False


def start_ollama_service():
    """启动并验证Ollama服务（仅当使用Ollama时）"""
    if _STATE["ai_backend"] == "qwen":
        # 如果使用Qwen，则跳过Ollama服务启动
        print("[INFO] 使用Qwen后端，跳过Ollama服务启动")
        return True

    subprocess.run('taskkill /f /im ollama.exe >NUL 2>&1', shell=True)
    time.sleep(0.5)

    ollama_exe = "ollama.exe"
    default_path = "C:\\Users\\Administrator\\AppData\\Local\\Programs\\Ollama\\ollama.exe"
    if os.path.exists(default_path):
        ollama_exe = default_path

    try:
        os.environ["OLLAMA_HOST"] = "127.0.0.1:11434"
        subprocess.Popen(
            [ollama_exe, "serve"],
            creationflags=subprocess.CREATE_NEW_CONSOLE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    except Exception as e:
        print(f"[ERROR] Ollama启动失败: {str(e)[:50]}")
        return False

    for _ in range(15):
        try:
            if requests.get(f"{CONFIG['ollama']['host']}/api/tags", timeout=1).status_code == 200:
                print("[INFO] Ollama服务就绪")
                return True
        except:
            time.sleep(1)
    print("[WARNING] Ollama连接超时，继续运行")
    return True


# ====================== 语音交互模块 ======================
try:
    from voice_interaction import VoiceInteraction, VoiceInteractionConfig, get_voice_interaction_instance, \
        is_voice_interaction_available

    VOICE_INTERACTION_AVAILABLE = is_voice_interaction_available()


    def setup_voice_interaction():
        """设置语音交互功能"""
        if not VOICE_INTERACTION_AVAILABLE:
            print("[WARNING] 语音交互功能不可用，缺少依赖库（speech_recognition, pyaudio）")
            return False

        config = VoiceInteractionConfig()

        # 询问用户是否启用语音交互
        print("\n===== 语音交互配置 =====")
        choice = input("是否启用语音交互功能? (y/N): ").strip().lower()
        if choice not in ('y', 'yes'):
            print("[INFO] 语音交互功能已禁用")
            return False

        # 设置唤醒词
        wake_word = input(f"请输入唤醒词 (默认: {config.wake_word}): ").strip()
        if wake_word:
            config.wake_word = wake_word

        # 设置唤醒超时
        wake_timeout = input(f"请输入唤醒后等待指令的超时时间 (默认: {config.wake_timeout}秒): ").strip()
        if wake_timeout.isdigit():
            config.wake_timeout = int(wake_timeout)

        # 设置是否使用在线识别
        online_recognition = input(f"是否优先使用在线语音识别 (需要网络)? (Y/n): ").strip().lower()
        config.online_recognition = online_recognition not in ('n', 'no')

        # 设置TTS引擎
        print("\nTTS引擎选择:")
        print("1. 系统默认引擎 (Windows: SAPI, Linux: espeak)")
        print("2. pyttsx3 (跨平台)")
        print("3. espeak (Linux)")
        tts_choice = input("请选择TTS引擎 (1-3, 默认: 1): ").strip()
        if tts_choice == "2":
            config.tts_engine = "pyttsx3"
        elif tts_choice == "3":
            config.tts_engine = "espeak"
        else:
            config.tts_engine = "system"

        # 设置音量和语速
        volume = input(f"请输入音量 (0-100, 默认: {config.volume}): ").strip()
        if volume.isdigit() and 0 <= int(volume) <= 100:
            config.volume = int(volume)

        rate = input(f"请输入语速 (-10到10, 默认: {config.rate}): ").strip()
        if rate.isdigit() and -10 <= int(rate) <= 10:
            config.rate = int(rate)

        # 创建语音交互实例
        voice_interaction = get_voice_interaction_instance(config)

        # 设置AI后端
        voice_interaction.set_ai_backend(
            _STATE["ai_backend"],
            _STATE["selected_model"],
            os.getenv("QWEN_API_KEY")
        )

        # 设置回调函数
        def on_ai_response(response):
            """处理AI响应回调"""
            if response == "exit":
                _STATE["running"] = False
            elif response == "switch_mode":
                # 切换运行模式
                if _STATE["mode"] == "camera":
                    _STATE["mode"] = "websocket"
                    print("[INFO] 切换到树莓派WebSocket模式")
                    # 启动WebSocket客户端
                    threading.Thread(target=start_websocket_worker, daemon=True).start()
                else:
                    _STATE["mode"] = "camera"
                    print("[INFO] 切换到本机摄像头模式")
                    # 启动摄像头线程
                    threading.Thread(target=camera_worker, daemon=True).start()

        config.on_ai_response = on_ai_response

        # 设置停止当前语音播报的回调
        def stop_current_speech():
            """停止当前正在播报的语音"""
            if _STATE["tts_speaker"]:
                try:
                    # 尝试停止TTS引擎
                    _STATE["tts_speaker"].Speak("", 3)  # 3表示立即停止
                except:
                    pass

        config.on_stop_speech = stop_current_speech

        # 启动语音交互
        if voice_interaction.start():
            _STATE["voice_interaction"] = voice_interaction
            _STATE["voice_interaction_enabled"] = True
            print("[INFO] 语音交互功能已启用")
            return True
        else:
            print("[WARNING] 语音交互功能启动失败")
            return False

except ImportError:
    VOICE_INTERACTION_AVAILABLE = False


    def setup_voice_interaction():
        """语音交互功能不可用的占位函数"""
        print("[WARNING] 语音交互功能不可用，voice_interaction模块未找到")
        return False

# ====================== Websocket语音发包 ======================
try:
    from pcsend import send_text_to_pi, is_pi_connected, setup_voice_sender, cleanup_voice_sender
except ImportError:
    # 如果无法导入，定义空函数
    def send_text_to_pi(text: str) -> bool:
        return False


    def is_pi_connected() -> bool:
        return False


    def setup_voice_sender(callback=None):
        pass


    def cleanup_voice_sender():
        pass


# ====================== TTS语音播报 ======================
def init_tts():
    """初始化TTS语音引擎"""
    try:
        speaker = win32com.client.Dispatch("SAPI.SpVoice")
        for voice in speaker.GetVoices():
            if "zh-CN" in voice.Id:
                speaker.Voice = voice
                break
        speaker.Volume = 100
        speaker.Rate = 0
        return speaker
    except:
        print("[ERROR] TTS引擎初始化失败")
        return None


def speak_async(text):
    """异步语音播报"""

    def _speak():
        if _STATE["tts_speaker"] and text:
            try:
                _STATE["tts_speaker"].Speak(text)
            except:
                pass

    threading.Thread(target=_speak, daemon=True).start()


def speak_voice(text: str) -> None:
    """语音输出函数（在websocket模式下发送到pi，禁用本地播报）"""
    if _STATE["mode"] == "websocket":
        # 在websocket模式下，总是尝试发送到树莓派，添加[voice]前缀
        full_text = f"[voice]{text}"
        if send_text_to_pi(full_text):
            print(f"[INFO] 已发送到树莓派: {full_text}")
        else:
            print(f"[WARNING] 发送到树莓派失败: {full_text}")
    else:
        # 在本机摄像头模式下，仍然使用原来的逻辑
        if _PI_OUTPUT is not None and _PI_OUTPUT.connected:
            _PI_OUTPUT.send(text)
            print(f"[INFO] 已发送到树莓派: {text}")
        else:
            speak_async(text)


# ====================== Pi 输出转发服务（可选） ======================
import queue


class PiOutputService:
    """在独立线程中维护到树莓派的 websocket 连接，并按序发送文本消息。"""

    def __init__(self):
        self.host = CONFIG["websocket"]["host"]
        self.port = CONFIG["websocket"]["port"]
        self.uri = f"ws://{self.host}:{self.port}"
        self._q: queue.Queue = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self.connected = False
        self._stop_event = threading.Event()

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self):
        try:
            self._stop_event.set()
            self._q.put_nowait(None)
        except Exception:
            pass
        if self._thread:
            self._thread.join(timeout=2.0)

    def send(self, text: str) -> None:
        try:
            self._q.put_nowait(text)
        except Exception:
            pass

    def _run_loop(self):
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
        import websockets as _websockets
        retry_interval = 3
        while not self._stop_event.is_set():
            try:
                async with _websockets.connect(self.uri, ping_interval=None, max_size=None) as ws:
                    self.connected = True
                    while not self._stop_event.is_set():
                        try:
                            text = await asyncio.get_event_loop().run_in_executor(None, self._q.get)
                        except Exception:
                            text = None
                        if text is None:
                            break
                        try:
                            await ws.send(str(text))
                        except Exception:
                            try:
                                self._q.put_nowait(text)
                            except Exception:
                                pass
                            break
            except Exception:
                self.connected = False
                await asyncio.sleep(retry_interval)
                continue
        self.connected = False


# 单例
_PI_OUTPUT: Optional[PiOutputService] = None


def select_pi_output():
    """询问用户是否将输出文本发送到树莓派（pisend.py）。"""
    # 如果是websocket模式，自动启用pcsend
    if _STATE["mode"] == "websocket":
        setup_voice_sender()
        return True

    global _PI_OUTPUT
    try:
        choice = input("是否将输出文字发送到树莓派以由树莓派播报? (y/N): ").strip().lower()
        if choice in ('y', 'yes'):
            _PI_OUTPUT = PiOutputService()
            _PI_OUTPUT.start()
            print("[INFO] 已启用向树莓派发送输出文本（后台连接中）")
            return True
    except Exception:
        pass
    print("[INFO] 将在本地进行语音播报（未启用向树莓派发送）")
    return False


# ====================== 连接失败交互选择 ======================
def ws_connection_failed_choice():
    """WebSocket连接失败时，让用户选择继续重试或退出"""
    print("\n===== 连接失败选择 =====")
    print(
        "1. 继续重试连接树莓派（最多剩余{}次）".format(CONFIG["ws_retry"]["max_attempts"] - _STATE["ws_retry_attempts"]))
    print("2. 切换到本机摄像头模式运行")
    print("3. 正常退出程序")
    while True:
        try:
            choice = input("\n请输入选择序号: ").strip()
            if not choice.isdigit():
                print("请输入有效的数字序号")
                continue
            choice_idx = int(choice)
            if choice_idx == 1:
                print(f"\n[INFO] 将在{CONFIG['ws_retry']['interval']}秒后重试连接...")
                time.sleep(CONFIG["ws_retry"]["interval"])
                return "retry"
            elif choice_idx == 2:
                _STATE["mode"] = "camera"
                print("\n[INFO] 切换到本机摄像头模式运行")
                speak_async("树莓派连接失败，切换到本机摄像头模式")
                return "switch_camera"
            elif choice_idx == 3:
                _STATE["running"] = False
                print("\n[INFO] 正在退出程序...")
                speak_async("程序已退出")
                return "exit"
            else:
                print("请输入1、2或3")
        except:
            print("输入无效，请重新选择")


# ====================== 双模式图像获取 ======================
def select_run_mode():
    """选择运行模式：本机摄像头 / 树莓派WebSocket"""
    print("\n===== 运行模式选择 =====")
    print("1. 本机摄像头模式")
    print("2. 树莓派WebSocket模式")
    while True:
        try:
            choice = input("\n请输入模式序号: ").strip()
            if not choice.isdigit():
                print("请输入有效的数字序号")
                continue
            choice_idx = int(choice)
            if choice_idx == 1:
                _STATE["mode"] = "camera"
                print("\n[INFO] 已选择：本机摄像头模式")
                break
            elif choice_idx == 2:
                _STATE["mode"] = "websocket"
                print(
                    f"\n[INFO] 已选择：树莓派WebSocket模式（地址：ws://{CONFIG['websocket']['host']}:{CONFIG['websocket']['port']}）")
                break
            else:
                print("请输入1或2")
        except:
            print("输入无效，请重新选择")
    return True


def camera_worker():
    """本机摄像头采集线程"""
    cap = None
    indexes = [0, 1]
    apis = [cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY]
    for idx in indexes:
        for api in apis:
            cap = cv2.VideoCapture(idx, api)
            if cap.isOpened():
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, CONFIG["camera"]["resolution"][0])
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CONFIG["camera"]["resolution"][1])
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                print("[INFO] 本机摄像头初始化成功")
                break
        if cap and cap.isOpened():
            break

    while _STATE["running"] and _STATE["mode"] == "camera":
        if cap and cap.isOpened():
            try:
                ret, frame = cap.read()
                if ret:
                    _STATE["frame_buffer"] = frame.copy()
            except:
                pass
        time.sleep(0.01)

    if cap:
        cap.release()


async def websocket_client():
    """WebSocket客户端：接收树莓派视频流（含重试逻辑）"""
    uri = f"ws://{CONFIG['websocket']['host']}:{CONFIG['websocket']['port']}"
    print(f"[INFO] 正在连接树莓派WebSocket服务器：{uri}")

    while _STATE["running"] and _STATE["mode"] == "websocket":
        try:
            async with websockets.connect(
                    uri,
                    ping_interval=None,
                    max_size=None,
                    compression=None,
                    close_timeout=0.1
            ) as websocket:
                _STATE["ws_connected"] = True
                _STATE["ws_retry_attempts"] = 0  # 连接成功重置重试次数
                print("[INFO] 树莓派WebSocket连接成功，开始接收视频流...")
                speak_async("树莓派连接成功，开始接收视频流")

                while _STATE["running"] and _STATE["mode"] == "websocket":
                    try:
                        frame_data = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                        nparr = np.frombuffer(frame_data, np.uint8)
                        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                        if frame is not None and frame.size > 0:
                            frame = cv2.resize(frame, CONFIG["camera"]["resolution"])
                            _STATE["frame_buffer"] = frame.copy()
                    except asyncio.TimeoutError:
                        continue
                    except websockets.exceptions.ConnectionClosed:
                        print("[ERROR] 树莓派WebSocket连接断开")
                        _STATE["ws_connected"] = False
                        speak_async("树莓派连接断开")
                        break
                    except Exception as e:
                        print(f"[ERROR] WebSocket接收异常: {str(e)[:50]}")
                        continue
        except Exception as e:
            _STATE["ws_retry_attempts"] += 1
            print(f"[ERROR] 第{_STATE['ws_retry_attempts']}次连接失败: {str(e)[:50]}")
            # 判断是否达到最大重试次数
            if _STATE["ws_retry_attempts"] >= CONFIG["ws_retry"]["max_attempts"]:
                choice = ws_connection_failed_choice()
                if choice == "retry":
                    _STATE["ws_retry_attempts"] = 0  # 重置重试次数，继续重试
                elif choice == "switch_camera":
                    # 启动本机摄像头线程，退出WS循环
                    threading.Thread(target=camera_worker, daemon=True).start()
                    break
                elif choice == "exit":
                    break
            else:
                # 未达最大次数，自动重试
                print(
                    f"[INFO] {CONFIG['ws_retry']['interval']}秒后自动重试（剩余{CONFIG['ws_retry']['max_attempts'] - _STATE['ws_retry_attempts']}次）")
                time.sleep(CONFIG["ws_retry"]["interval"])


def start_websocket_worker():
    """启动WebSocket客户端线程"""

    def _run_ws():
        _STATE["ws_loop"] = asyncio.new_event_loop()
        asyncio.set_event_loop(_STATE["ws_loop"])
        _STATE["ws_task"] = _STATE["ws_loop"].create_task(websocket_client())
        try:
            _STATE["ws_loop"].run_until_complete(_STATE["ws_task"])
        except:
            pass

    ws_thread = threading.Thread(target=_run_ws, daemon=True)
    ws_thread.start()
    time.sleep(2)


# ====================== 图像识别 ======================
def infer_frame():
    """图像推理（根据选择的后端）"""
    if _STATE["ai_backend"] == "ollama":
        # 使用Ollama进行推理
        try:
            _, buf = cv2.imencode('.jpg', _STATE["frame_buffer"], [cv2.IMWRITE_JPEG_QUALITY, 90])
            b64 = base64.b64encode(buf).decode()
            prompt = """请精准描述画面内容，控制在15字以内，仅返回描述文本"""
            payload = {
                "model": _STATE["selected_model"],
                "prompt": prompt,
                "images": [b64],
                "stream": False,
                "options": {
                    "temperature": 0.01,
                    "num_predict": 100,
                    "top_p": 0.1,
                    "gpu_layers": CONFIG["gpu"]["layers"]
                }
            }
            resp = requests.post(
                f"{CONFIG['ollama']['host']}/api/generate",
                json=payload,
                timeout=CONFIG["inference"]["timeout"]
            )
            if resp.status_code == 200:
                result = resp.json()["response"].strip().replace("\n", "").replace(" ", "")[:15]
                print(f"[INFO] Ollama识别结果: {result}")
                # 识别结果属于 VOICE 输出，使用 speak_voice（优先发送到Pi）
                speak_voice(result)
            else:
                speak_voice("Ollama识别失败")
        except Exception as e:
            print(f"[ERROR] Ollama推理异常: {str(e)[:50]}")
            speak_voice("识别失败")

    elif _STATE["ai_backend"] == "qwen":
        # 使用Qwen进行推理
        try:
            # 直接调用Qwen分析
            from qwen_integration import QwenAnalyzer
            import os

            # 从环境变量或配置文件中获取API密钥
            api_key = os.getenv("QWEN_API_KEY")
            if not api_key:
                # 如果没有环境变量，则可以检查是否有配置文件
                import configparser
                config = configparser.ConfigParser()
                if config.read('config.ini') and 'qwen' in config and 'api_key' in config['qwen']:
                    api_key = config['qwen']['api_key']

            if api_key:
                # 初始化Qwen分析器
                qwen_analyzer = QwenAnalyzer(api_key)
                # 将帧转换为字节
                _, img_encoded = cv2.imencode('.jpg', _STATE["frame_buffer"], [cv2.IMWRITE_JPEG_QUALITY, 90])
                image_bytes = img_encoded.tobytes()
                # 使用Qwen分析图像
                prompt = "请精准描述画面内容，控制在30字以内，仅返回描述文本"
                result = qwen_analyzer.analyze_image(image_bytes, prompt)
                if result:
                    description = qwen_analyzer.extract_description(result)
                    # 限制返回结果长度
                    result_text = description[:15]
                    print(f"[INFO] Qwen3.5-Plus识别结果: {result_text}")
                    # 识别结果属于 VOICE 输出，使用 speak_voice（优先发送到Pi）
                    speak_voice(result_text)
                else:
                    speak_voice("Qwen识别失败")
            else:
                speak_voice("Qwen API密钥未配置")
        except ImportError:
            print("[ERROR] 未找到Qwen集成模块")
            speak_voice("Qwen模块缺失")
        except Exception as e:
            print(f"[ERROR] Qwen推理异常: {str(e)[:50]}")
            speak_voice("Qwen识别失败")


# ====================== 主程序 ======================
def main():
    """主程序入口"""
    if os.name == 'nt' and not ctypes.windll.shell32.IsUserAnAdmin():
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, __file__, None, 1)
        return

    print("=" * 60)
    print("实时视频分析系统 - 树莓派/PC双模式版")
    print("=" * 60)

    if not check_dependencies():
        input("\n按回车退出...")
        return

    # 首先选择AI后端
    if not select_ai_backend():
        input("\n按回车退出...")
        return

    if not select_run_mode():
        input("\n按回车退出...")
        return

    if not select_model():
        input("\n按回车退出...")
        return

    if not pull_ollama_model():
        input("\n按回车退出...")
        return

    if not start_ollama_service():
        input("\n按回车退出...")
        return

    _STATE["tts_speaker"] = init_tts()

    # 询问是否启用语音交互功能
    try:
        if VOICE_INTERACTION_AVAILABLE:
            if setup_voice_interaction():
                _STATE["voice_interaction_enabled"] = True
        else:
            print("[INFO] 语音交互功能不可用，需要安装speech_recognition和pyaudio")
    except Exception as e:
        print(f"[WARNING] 语音交互功能初始化失败: {str(e)}")

    # 询问是否将输出发送到树莓派；若选择，将在后台维护连接并路由speak_async
    try:
        select_pi_output()
    except Exception:
        pass

    if _STATE["tts_speaker"]:
        backend_name = "Qwen3.5-Plus" if _STATE["ai_backend"] == "qwen" else _STATE["selected_model"]
        # 启动提示
        speak_voice(f"系统已启动，{_STATE['mode']}模式，使用{backend_name}进行分析")

    if _STATE["mode"] == "camera":
        threading.Thread(target=camera_worker, daemon=True).start()
    elif _STATE["mode"] == "websocket":
        start_websocket_worker()

    cv2.namedWindow("Video Analysis (Raspberry Pi/PC)", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("Video Analysis (Raspberry Pi/PC)", CONFIG["display"]["width"], CONFIG["display"]["height"])

    last_infer = 0
    while _STATE["running"]:
        current = time.time()
        if current - last_infer >= CONFIG["inference"]["interval"] and not np.all(_STATE["frame_buffer"] == 0):
            infer_frame()
            last_infer = current

        cv2.imshow("Video Analysis (Raspberry Pi/PC)", _STATE["frame_buffer"])
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            _STATE["running"] = False
            break
        elif key == ord('m'):
            print("\n===== 切换运行模式 =====")
            select_run_mode()
            if _STATE["mode"] == "camera":
                threading.Thread(target=camera_worker, daemon=True).start()
            elif _STATE["mode"] == "websocket":
                start_websocket_worker()

    cv2.destroyAllWindows()
    if _STATE["ws_loop"]:
        _STATE["ws_loop"].stop()
    try:
        subprocess.run('taskkill /f /im ollama.exe >NUL 2>&1', shell=True)
    except:
        pass
    if _STATE["tts_speaker"]:
        # 退出消息
        speak_voice("系统已退出")
    # 停止 Pi 输出服务（如果启用）将在退出处理处执行
    try:
        if _PI_OUTPUT is not None:
            _PI_OUTPUT.stop()
    except Exception:
        pass
    # 清理 pcsend 资源
    try:
        cleanup_voice_sender()
    except Exception:
        pass
    # 停止语音交互服务
    try:
        if _STATE["voice_interaction_enabled"] and _STATE["voice_interaction"]:
            _STATE["voice_interaction"].stop()
    except Exception:
        pass


if __name__ == "__main__":
    main()