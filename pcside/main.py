#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
main.py - PC端主程序
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
import json
from typing import Optional, Dict, Any, List
import websockets

# ==================== 尝试导入中文渲染库 ====================
try:
    from PIL import Image, ImageDraw, ImageFont

    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# ==================== 核心环境注入 ====================
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)  # 获取上一级作为项目根目录
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# ==================== 导入真实核心模块 ====================
try:
    from core.config import get_config, set_config
    from core.logger import console_info, console_error, console_prompt
    from core.tts import speak_async
    from core.voice_interaction import get_voice_interaction, is_voice_interaction_available, VoiceInteractionConfig
    from core.ai_backend import list_ollama_models, analyze_image
    from core.network import get_local_ip, get_network_prefix
except ImportError as init_err:
    print(f"\n\033[91m[致命错误] 无法导入核心模块，请检查代码结构！\033[0m")


    def get_config(k: str, d: Any = None) -> Any:
        return d


    def set_config(k: str, v: Any) -> None:
        pass


    def console_info(t: str) -> None:
        pass


    def console_error(t: str) -> None:
        pass


    def console_prompt(t: str) -> None:
        pass


    def speak_async(t: str) -> None:
        pass


    def get_voice_interaction(c: Any) -> Any:
        return None


    def is_voice_interaction_available() -> bool:
        return False


    class VoiceInteractionConfig:
        pass


    def list_ollama_models() -> List[str]:
        return []


    def analyze_image(f: Any, m: str) -> str:
        return "识别失败"


    def get_local_ip() -> str:
        return "127.0.0.1"


    def get_network_prefix() -> str:
        return "192.168.31."


    sys.exit(1)

# ==================== 全局状态与队列 ====================
_STATE: Dict[str, Any] = {
    "running": True,
    "video_running": False,
    "connection_lost": False,
    "mode": "",
    "frame_buffer": None,
    "selected_model": "",
    "ai_backend": "",
}

inference_queue: queue.Queue = queue.Queue(maxsize=1)
pc_text_queue: queue.Queue = queue.Queue(maxsize=5)
latest_inference_result: Dict[str, Any] = {"text": "", "timestamp": 0}

# ==================== 全局日志记录系统 ====================
_LOG_RECORDS: List[str] = []


def _add_log(level: str, text: str) -> None:
    log_line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [{level}] {text}"
    _LOG_RECORDS.append(log_line)


def safe_console_info(text: str) -> None:
    _add_log("INFO", text)
    if console_info:
        console_info(text)
    else:
        print(f"[INFO] {text}")


def safe_console_error(text: str) -> None:
    _add_log("ERROR", text)
    if console_error:
        console_error(text)
    else:
        print(f"\033[91m[ERROR] {text}\033[0m")


def safe_console_prompt(text: str) -> None:
    _add_log("PROMPT", text)
    if console_prompt:
        console_prompt(text)
    else:
        print(text)


def export_log() -> None:
    # ★ 需求2修复：指定项目根目录下的 log 文件夹
    log_dir = os.path.join(project_root, "log")
    try:
        if not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)
    except Exception as e:
        print(f"创建 log 文件夹失败，将使用当前目录。原因: {e}")
        log_dir = os.getcwd()

    filename = f"{time.strftime('%Y%m%d_%H%M%S')}_PC运行日志.txt"
    filepath = os.path.join(log_dir, filename)
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write("\n".join(_LOG_RECORDS))
        print(f"\n✅ 程序结束，运行日志已导出至: {filepath}")
    except Exception as e:
        print(f"\n❌ 日志导出失败: {e}")


# ==================== UI 渲染助手 (中文支持) ====================
def draw_chinese_text(img_np, text, position, text_color=(0, 255, 0), font_size=25):
    if not HAS_PIL:
        cv2.putText(img_np, text, position, cv2.FONT_HERSHEY_SIMPLEX, 0.8, text_color, 2)
        return img_np
    try:
        pil_img = Image.fromarray(cv2.cvtColor(img_np, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(pil_img)
        font = None
        for font_name in ["msyh.ttc", "simhei.ttf", "simsun.ttc", "Arial.ttf"]:
            try:
                font = ImageFont.truetype(font_name, font_size)
                break
            except Exception:
                pass
        if font is None:
            font = ImageFont.load_default()

        bbox = draw.textbbox(position, text, font=font)
        draw.rectangle([bbox[0] - 5, bbox[1] - 5, bbox[2] + 5, bbox[3] + 5], fill=(0, 0, 0))
        draw.text(position, text, font=font, fill=text_color)

        return cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
    except Exception:
        cv2.putText(img_np, text, position, cv2.FONT_HERSHEY_SIMPLEX, 0.8, text_color, 2)
        return img_np


# ==================== 核心防打架：全局输出流拦截器 ====================
class ThreadSafePrintSuppressor:
    def __init__(self, original_stream):
        self.original_stream = original_stream

    def write(self, text):
        if not _STATE["video_running"] and threading.current_thread().name == "AI_Inference_Thread":
            return
        self.original_stream.write(text)

    def flush(self):
        self.original_stream.flush()


sys.stdout = ThreadSafePrintSuppressor(sys.stdout)
sys.stderr = ThreadSafePrintSuppressor(sys.stderr)


# ==================== 独立后台推理线程 ====================
class InferenceThread(threading.Thread):
    def __init__(self, interval: int, backend: str, model: str):
        super().__init__(name="AI_Inference_Thread", daemon=True)
        self.interval = interval
        self.backend = backend
        self.model = model

    def run(self) -> None:
        last_infer_time = 0.0
        try:
            import core.ai_backend as ai_be
            if not hasattr(ai_be, '_STATE'): ai_be._STATE = {}
            ai_be._STATE["ai_backend"] = self.backend

            original_logger_info = getattr(ai_be, 'console_info', None)

            def silenced_logger_info(t):
                if _STATE["video_running"]:
                    if original_logger_info: original_logger_info(t)

            ai_be.console_info = silenced_logger_info
        except Exception:
            pass

        while _STATE["running"]:
            if not _STATE["video_running"]:
                time.sleep(0.5)
                continue

            try:
                frame = inference_queue.get(timeout=0.1)
                if time.time() - last_infer_time < self.interval:
                    continue

                try:
                    result = analyze_image(frame, self.model)

                    if not _STATE["video_running"] or _STATE["connection_lost"]:
                        continue

                    if result and result != "识别失败":
                        latest_inference_result["text"] = result
                        latest_inference_result["timestamp"] = time.time()
                        safe_console_info(f"AI 分析完成: {result}")

                        if _STATE["mode"] == "websocket":
                            try:
                                pc_text_queue.put_nowait(result)
                            except queue.Full:
                                pass
                        else:
                            if speak_async: speak_async(result)

                except Exception as infer_err:
                    if _STATE["video_running"]:
                        safe_console_error(f"识别过程异常: {str(infer_err)[:50]}")

                last_infer_time = time.time()
            except queue.Empty:
                continue
            except Exception:
                time.sleep(0.5)


# ==================== 系统与网络发现 ====================
def is_admin() -> bool:
    try:
        if os.name != 'nt': return True
        is_user_an_admin = getattr(ctypes.windll.shell32, "IsUserAnAdmin", None)
        return bool(is_user_an_admin()) if is_user_an_admin else False
    except Exception:
        return False


def run_as_admin() -> bool:
    if os.name != 'nt': return False
    try:
        if is_admin(): return True
        shell_exec = getattr(ctypes.windll.shell32, "ShellExecuteW", None)
        if shell_exec: shell_exec(None, "runas", sys.executable, " ".join(sys.argv), None, 1)
        return True
    except Exception:
        return False


def check_dependencies() -> bool:
    required_packages = {
        "cv2": "opencv-python",
        "numpy": "numpy",
        "requests": "requests",
        "websockets": "websockets",
        "asyncio": "asyncio",
        "PIL": "Pillow"
    }
    missing_pkgs = []
    for pkg, install_name in required_packages.items():
        try:
            __import__(pkg)
        except ImportError:
            missing_pkgs.append(install_name)
    if missing_pkgs:
        safe_console_error(f"缺失依赖包 (请通过 pip install 安装): {', '.join(missing_pkgs)}")
        return False
    return True


def _is_port_open(ip: str, port: int) -> bool:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.3)
        res = sock.connect_ex((ip, port))
        sock.close()
        return res == 0
    except Exception:
        return False


def discover_raspberry_pi() -> Optional[str]:
    safe_console_info("正在启动网络扫描，寻找树莓派...")
    known_pi_ip = get_config("network.pi_ip", "192.168.31.31") if get_config else "192.168.31.31"

    if known_pi_ip and known_pi_ip != "127.0.0.1":
        safe_console_info(f"尝试连接已知树莓派地址: {known_pi_ip}")
        if _is_port_open(known_pi_ip, 8001):
            safe_console_info(f"✅ 成功连接到已知树莓派: {known_pi_ip}")
            return known_pi_ip

    safe_console_info("向局域网发送 UDP 发现广播 (端口 50000)...")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.settimeout(2.0)

    msg = json.dumps({'type': 'pc_discovery', 'service': 'video_analysis'}).encode('utf-8')
    try:
        sock.sendto(msg, ('<broadcast>', 50000))
        safe_console_info("广播已发送，等待树莓派响应 (最多等待2秒)...")
        while True:
            data, addr = sock.recvfrom(1024)
            resp = json.loads(data.decode('utf-8'))
            if resp.get('type') == 'raspberry_pi_response':
                pi_ip = resp.get('ip', addr[0])
                safe_console_info(f"✅ 成功发现树莓派: {pi_ip}")
                return pi_ip
    except socket.timeout:
        safe_console_info("⚠️ UDP 广播超时，未收到响应。")
    except Exception:
        pass
    finally:
        sock.close()
    return None


def setup_pi_network() -> bool:
    safe_console_prompt("\n===== 树莓派网络连接 =====")
    pi_ip = discover_raspberry_pi()
    if pi_ip:
        if set_config:
            set_config("network.pi_ip", pi_ip)
            set_config("websocket.host", pi_ip)
        return True
    else:
        manual = input("[INFO] 未自动发现树莓派，请输入 IP (输入 q 返回): ").strip()
        if manual.lower() == 'q': return False
        if manual:
            if set_config:
                set_config("network.pi_ip", manual)
                set_config("websocket.host", manual)
            return True
        return False


# ==================== 菜单选择逻辑 ====================
def select_ai_backend() -> bool:
    safe_console_prompt("\n===== AI后端选择 =====")
    safe_console_prompt("1. Ollama (本地模型)")
    safe_console_prompt("2. Qwen3.5-Plus (云端模型)")
    while True:
        choice = input("\n请选择AI后端 (1 或 2): ").strip()
        if choice == "1":
            _STATE["ai_backend"] = "ollama"
            safe_console_info("已选择: Ollama 本地引擎")
            return True
        elif choice == "2":
            _STATE["ai_backend"] = "qwen"
            safe_console_info("已选择: Qwen 云端引擎")
            return True


def select_model() -> bool:
    if _STATE["ai_backend"] == "qwen":
        _STATE["selected_model"] = "qwen-vl-max"
        return True

    if not list_ollama_models or not get_config: return False

    safe_console_prompt("\n===== 模型选择 =====")
    local_models = list_ollama_models()
    default_models = get_config("ollama.default_models", ["llava:7b-v1.5-q4_K_M"])
    all_models = list(set(default_models + local_models))
    all_models.sort()

    for idx, model in enumerate(all_models, 1):
        status = "[已安装]" if model in local_models else "[需下载]"
        safe_console_prompt(f"{idx}. {model} {status}")
    safe_console_prompt(f"{len(all_models) + 1}. 自定义模型")

    while True:
        choice = input("\n请输入模型序号: ").strip()
        if choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(all_models):
                _STATE["selected_model"] = all_models[idx - 1]
                break
            elif idx == len(all_models) + 1:
                _STATE["selected_model"] = input("请输入模型名称: ").strip()
                break

    safe_console_info(f"已锁定模型: {_STATE['selected_model']}")
    return True


def select_run_mode() -> bool:
    safe_console_prompt("\n===== 运行模式选择 =====")
    safe_console_prompt("1. 本机摄像头模式")
    safe_console_prompt("2. 树莓派WebSocket模式")
    safe_console_prompt("q. 退出程序")
    while True:
        choice = input("\n请输入模式序号: ").strip().lower()
        if choice == 'q':
            _STATE["running"] = False
            return False
        if choice == "1":
            _STATE["mode"] = "camera"
            return True
        elif choice == "2":
            _STATE["mode"] = "websocket"
            return True


# ==================== 工作流与通信线程 ====================
def camera_worker() -> None:
    cap = cv2.VideoCapture(0)
    while _STATE["video_running"] and _STATE["mode"] == "camera":
        ret, frame = cap.read()
        if ret:
            _STATE["frame_buffer"] = cv2.resize(frame, (1280, 720))
        time.sleep(0.01)
    if cap: cap.release()


async def websocket_client() -> None:
    pi_ip = get_config('network.pi_ip', '192.168.31.31') if get_config else '192.168.31.31'
    uri = f"ws://{pi_ip}:8001"

    try:
        async with websockets.connect(uri, ping_interval=None, ping_timeout=None, max_size=None) as ws:
            safe_console_info(f"✅ 树莓派 WebSocket 全双工通道已连接 ({uri})")

            async def recv_video() -> None:
                try:
                    async for data in ws:
                        if not _STATE["video_running"]: break
                        arr = np.frombuffer(data, np.uint8)
                        frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                        if frame is not None:
                            _STATE["frame_buffer"] = cv2.resize(frame, (1280, 720))
                except Exception:
                    pass

            async def send_text() -> None:
                while _STATE["video_running"]:
                    try:
                        text = pc_text_queue.get_nowait()
                        await ws.send(text)
                    except queue.Empty:
                        await asyncio.sleep(0.1)
                    except Exception:
                        break

            tasks = [asyncio.create_task(recv_video()), asyncio.create_task(send_text())]
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for t in tasks: t.cancel()

            # ★ 需求1修复：只要 websocket 任务结束（包含树莓派断电/停止），必须强制触发回退！
            if _STATE["video_running"]:
                safe_console_error("检测到远端设备主动终止连接")
                _STATE["connection_lost"] = True

    except Exception as ws_err:
        if _STATE["video_running"]:
            safe_console_error(f"连接断开或无法建立: {ws_err}")
            _STATE["connection_lost"] = True


def clear_queues():
    while not inference_queue.empty():
        try:
            inference_queue.get_nowait()
        except:
            pass
    while not pc_text_queue.empty():
        try:
            pc_text_queue.get_nowait()
        except:
            pass


def signal_handler(sig_num: Any, frame_data: Any) -> None:
    _STATE["running"] = False
    _STATE["video_running"] = False


# ==================== 主程序双循环入口 ====================
def main() -> None:
    signal.signal(signal.SIGINT, signal_handler)
    if not run_as_admin() and os.name == 'nt': pass

    safe_console_prompt("=" * 60)
    safe_console_prompt("实时视频分析系统 (精准断连回退版)")
    safe_console_prompt("=" * 60)

    if not check_dependencies(): return
    if not select_ai_backend(): return
    if not select_model(): return

    if _STATE["ai_backend"] == "ollama":
        safe_console_info("正在确保 Ollama 后台服务在线...")
        subprocess.run('taskkill /f /im ollama.exe >NUL 2>&1', shell=True)
        time.sleep(0.5)
        CREATE_NO_WINDOW = 0x08000000
        subprocess.Popen(
            ["ollama", "serve"],
            creationflags=CREATE_NO_WINDOW if os.name == 'nt' else 0,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        time.sleep(1)

    inf_interval = get_config("inference.interval", 5) if get_config else 5
    global_inf_thread = InferenceThread(inf_interval, _STATE["ai_backend"], _STATE["selected_model"])
    global_inf_thread.start()

    while _STATE["running"]:
        _STATE["connection_lost"] = False
        _STATE["video_running"] = False
        clear_queues()
        _STATE["frame_buffer"] = np.zeros((720, 1280, 3), np.uint8)

        if not select_run_mode(): break

        if _STATE["mode"] == "websocket":
            if not setup_pi_network(): continue

        _STATE["video_running"] = True
        global_inf_thread.backend = _STATE["ai_backend"]
        global_inf_thread.model = _STATE["selected_model"]

        if _STATE["mode"] == "camera":
            threading.Thread(target=camera_worker, daemon=True).start()
        else:
            def ws_worker() -> None:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(websocket_client())
                try:
                    loop.close()
                except:
                    pass

            threading.Thread(target=ws_worker, daemon=True).start()

        cv2.namedWindow("Video Analysis", cv2.WINDOW_NORMAL)
        cv2.resizeWindow("Video Analysis", 1280, 720)

        try:
            while _STATE["video_running"] and _STATE["running"]:
                if _STATE["connection_lost"]: break

                current_frame = _STATE["frame_buffer"]
                if isinstance(current_frame, np.ndarray):
                    img = current_frame.copy()

                    res = str(latest_inference_result["text"])
                    res_time = float(latest_inference_result["timestamp"])

                    if res and (time.time() - res_time < 10):
                        img = draw_chinese_text(img, f"AI: {res}", (20, 30))

                    cv2.imshow("Video Analysis", img)

                    try:
                        inference_queue.put_nowait(img)
                    except queue.Full:
                        try:
                            inference_queue.get_nowait()
                            inference_queue.put_nowait(img)
                        except queue.Empty:
                            pass

                key = cv2.waitKey(1) & 0xFF
                if key == ord('q'):
                    _STATE["video_running"] = False
                    break
        finally:
            _STATE["video_running"] = False
            cv2.destroyAllWindows()

        if _STATE["connection_lost"] and _STATE["running"]:
            safe_console_prompt("\n" + "-" * 50)
            safe_console_prompt("远端网络流结束，已清理底层流传输。")
            safe_console_prompt("即将为您回退到模式选择菜单...")
            safe_console_prompt("-" * 50 + "\n")
            time.sleep(1)

    subprocess.run('taskkill /f /im ollama.exe >NUL 2>&1', shell=True)
    sys.stdout = getattr(sys.stdout, 'original_stream', sys.stdout)
    sys.stderr = getattr(sys.stderr, 'original_stream', sys.stderr)
    export_log()


if __name__ == "__main__":
    main()