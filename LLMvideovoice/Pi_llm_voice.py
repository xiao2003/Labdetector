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
    "display": {"width": 1280, "height": 720},
    "ws_retry": {"max_attempts": 5, "interval": 3}  # WS重试配置：最多5次，间隔3秒
}

# 全局状态
_STATE = {
    "running": True,
    "mode": "",  # camera / websocket
    "frame_buffer": np.zeros((CONFIG["camera"]["resolution"][1], CONFIG["camera"]["resolution"][0], 3), np.uint8),
    "tts_speaker": None,
    "selected_model": "",
    "ws_connected": False,
    "ws_loop": None,
    "ws_task": None,
    "ws_retry_attempts": 0  # WS重试次数
}


# ====================== 依赖检查 & Ollama管理 ======================
def check_dependencies():
    """检查并自动安装所有依赖包"""
    required_packages = ["cv2", "numpy", "requests", "win32com.client", "websockets"]
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


def select_model():
    """命令行交互选择模型"""
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
    """自动拉取选中的模型（不存在时）"""
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
    """启动并验证Ollama服务"""
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
    """图像推理（使用选中的模型）"""
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
            print(f"[INFO] 识别结果: {result}")
            speak_async(result)
    except Exception as e:
        print(f"[ERROR] 推理异常: {str(e)[:50]}")
        speak_async("识别失败")


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
    if _STATE["tts_speaker"]:
        speak_async(f"系统已启动，{_STATE['mode']}模式，使用{_STATE['selected_model']}模型分析")

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
        speak_async("系统已退出")
    print("\n[INFO] 系统正常退出")


if __name__ == "__main__":
    main()