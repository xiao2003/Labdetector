#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
main.py - PC端主程序 (多节点独立重连 + ESC回退优化版)
"""
import asyncio
import cv2
import numpy as np
import threading
import subprocess
import ctypes
import os
import time
import socket
import signal
import queue
import json
import sys
import codecs
from typing import Optional, Dict, Any, List

from pcside.tools.version_manager import get_app_version
from pcside.core.scheduler_manager import scheduler_manager

APP_VERSION = get_app_version()

_builtin_input = input  # 保存 Python 原生的 input 函数


def safe_input(prompt=""):
    """安全包装器：遇到 PyCharm 发送的 0xff 等幽灵控制字符时，静默重试，绝不崩溃"""
    while True:
        try:
            return _builtin_input(prompt)
        except UnicodeDecodeError:
            pass


input = safe_input

try:
    from PIL import Image, ImageDraw, ImageFont

    HAS_PIL = True
except ImportError:
    HAS_PIL = False

current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)

if project_root not in sys.path:
    sys.path.insert(0, project_root)
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

try:
    from pcside.core.config import get_config, set_config
    from pcside.core.logger import console_info, console_error, console_prompt
    from pcside.core.tts import speak_async
    from pcside.core.ai_backend import list_ollama_models, analyze_image
    from pcside.core.network import get_local_ip, get_network_prefix
    from pcside.communication.network_scanner import get_lab_topology
    from pcside.communication.multi_ws_manager import MultiPiManager
    from pcside.voice.voice_interaction import get_voice_interaction
except ImportError as e:
    print(f"\n\033[91m[致命错误] 模块导入失败: {e}\033[0m")
    sys.exit(1)

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
latest_inference_result: Dict[str, Any] = {"text": "", "timestamp": 0}
_LOG_RECORDS: List[str] = []


def _add_log(level: str, text: str) -> None:
    _LOG_RECORDS.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [{level}] {text}")


def safe_console_info(text: str) -> None:
    _add_log("INFO", text)
    if console_info: console_info(text)


def safe_console_error(text: str) -> None:
    _add_log("ERROR", text)
    if console_error: console_error(text)


def safe_console_prompt(text: str) -> None:
    _add_log("PROMPT", text)
    if console_prompt: console_prompt(text)


def export_log() -> None:
    log_dir = os.path.join(current_dir, "log")
    os.makedirs(log_dir, exist_ok=True)
    filepath = os.path.join(log_dir, f"{time.strftime('%Y%m%d_%H%M%S')}_PC运行日志.txt")
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write("\n".join(_LOG_RECORDS))
        print(f"\n[INFO] 日志已导出至: {filepath}")
    except Exception as e:
        print(f"\n[ERROR] 日志导出失败: {e}")


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
            except:
                pass
        if font is None: font = ImageFont.load_default()
        bbox = draw.textbbox(position, text, font=font)
        draw.rectangle([bbox[0] - 5, bbox[1] - 5, bbox[2] + 5, bbox[3] + 5], fill=(0, 0, 0))
        draw.text(position, text, font=font, fill=text_color)
        return cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
    except:
        return img_np


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


class InferenceThread(threading.Thread):
    def __init__(self, interval: int, backend: str, model: str):
        super().__init__(name="AI_Inference_Thread", daemon=True)
        self.interval = interval
        self.backend = backend
        self.model = model

    def run(self) -> None:
        last_infer_time = 0.0
        try:
            import pcside.core.ai_backend as ai_be
            if not hasattr(ai_be, '_STATE'): ai_be._STATE = {}
            ai_be._STATE["ai_backend"] = self.backend
        except:
            pass

        while _STATE["running"]:
            if not _STATE["video_running"]:
                time.sleep(0.5)
                continue
            try:
                frame = inference_queue.get(timeout=0.1)
                if time.time() - last_infer_time < self.interval: continue
                result = analyze_image(frame, self.model)
                if result and result != "识别失败":
                    latest_inference_result["text"] = result
                    latest_inference_result["timestamp"] = time.time()
                    safe_console_info(f" 本机视觉分析完成: {result}")
                last_infer_time = time.time()
            except queue.Empty:
                continue
            except:
                time.sleep(0.5)


def is_admin() -> bool:
    try:
        if os.name != 'nt': return True
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except:
        return False


def run_as_admin() -> bool:
    if os.name != 'nt': return False
    try:
        if is_admin(): return True
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(sys.argv), None, 1)
        return True
    except:
        return False


def select_ai_backend():
    from pcside.core.config import set_config
    while True:
        try:
            print("\n" + "=" * 60)
            from pcside.tools.version_manager import get_app_version
            print(f"LabDetector 智能多模态实验室管家 V{get_app_version()}")
            print("=" * 60)
            print("\n===== AI后端选择 =====")
            print("[1]. Ollama (本地私有化大模型)")
            print("[2]. Qwen3.5-Plus (阿里云端模型)")

            choice = input("\n请选择大模型 (1 或 2，输入 exit 退出): ").strip().lower()

            if choice in ['q', 'quit', 'exit', '0']:
                print("\n[INFO] 接收到退出指令，正在中止启动流程...")
                raise KeyboardInterrupt

            if choice == '1':
                print("\n[INFO] 切换至 Ollama 本地后端...")
                set_config('ai_backend.type', 'ollama')
                _STATE["ai_backend"] = "ollama"
                return True
            elif choice == '2':
                print("\n[INFO] 切换至 Qwen 云端后端...")
                set_config('ai_backend.type', 'qwen')
                _STATE["ai_backend"] = "qwen"
                return True
            else:
                print("\n[WARN] 输入无效，请输入 1 或 2，或者输入 exit 退出。")

        except (KeyboardInterrupt, EOFError):
            raise


def select_model() -> bool:
    if _STATE["ai_backend"] == "qwen":
        _STATE["selected_model"] = get_config("qwen.model", "qwen-vl-max")
        return True

    safe_console_prompt("\n===== 模型选择 =====")
    local_models = list_ollama_models() if list_ollama_models else []
    raw_defaults = get_config("ollama.default_models", ["llava:7b-v1.5-q4_K_M"])

    if isinstance(raw_defaults, str):
        default_models = [m.strip() for m in raw_defaults.split(',') if m.strip()]
    elif isinstance(raw_defaults, list):
        default_models = raw_defaults
    else:
        default_models = []

    all_models = list(set(default_models + local_models))
    all_models.sort()

    for idx, model in enumerate(all_models, 1):
        status = "[已安装]" if model in local_models else "[需下载]"
        safe_console_prompt(f"{idx}. {model} {status}")
    safe_console_prompt(f"{len(all_models) + 1}. 自定义模型")

    while True:
        try:
            choice = input("\n请输入模型序号 (输入 exit 退出): ").strip().lower()

            if choice in ['q', 'quit', 'exit', '0']:
                print("\n[INFO] 接收到退出指令，正在中止启动流程...", flush=True)
                raise KeyboardInterrupt

            if choice.isdigit():
                idx = int(choice)
                if 1 <= idx <= len(all_models):
                    _STATE["selected_model"] = all_models[idx - 1]
                    break
                elif idx == len(all_models) + 1:
                    _STATE["selected_model"] = input("请输入自定义模型名称: ").strip()
                    break
                else:
                    print(f"\n[WARN] 序号超出范围，请输入 1 到 {len(all_models) + 1} 之间的数字。")
            else:
                print("\n[WARN] 输入无效，请输入有效数字序号，或输入 exit 退出。")
        except (KeyboardInterrupt, EOFError):
            raise

    safe_console_info(f"已锁定模型: {_STATE['selected_model']}")
    return True


def select_run_mode() -> bool:
    safe_console_prompt("\n===== 运行模式选择 =====")
    safe_console_prompt("1. 本机摄像头模式")
    safe_console_prompt("2. 树莓派集群WebSocket模式")
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


def signal_handler(sig_num: Any, frame_data: Any) -> None:
    _STATE["running"] = False
    _STATE["video_running"] = False


# ==================== 主程序入口 ====================
def main() -> None:
    signal.signal(signal.SIGINT, signal_handler)
    if not run_as_admin() and os.name == 'nt': pass

    try:
        if not select_ai_backend(): return
    except KeyboardInterrupt:
        return

    if _STATE["ai_backend"] == "ollama":
        subprocess.run('taskkill /f /im ollama.exe >NUL 2>&1', shell=True)
        CREATE_NO_WINDOW = 0x08000000
        subprocess.Popen(
            ["ollama", "serve"],
            creationflags=CREATE_NO_WINDOW if os.name == 'nt' else 0,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        time.sleep(1)

    voice_agent = get_voice_interaction()
    inf_interval = get_config("inference.interval", 5) if get_config else 5
    global_inf_thread = InferenceThread(inf_interval, _STATE["ai_backend"], "")
    global_inf_thread.start()

    scheduler_manager.start()

    try:
        # ★ 第一层循环：控制回退到“模型选择”
        while _STATE["running"]:
            if not select_model(): break

            global_inf_thread.model = _STATE["selected_model"]
            if voice_agent:
                voice_agent.set_ai_backend(_STATE["ai_backend"], _STATE["selected_model"])
                if not voice_agent.is_running:
                    def frame_provider():
                        return _STATE.get("frame_buffer")

                    voice_agent.get_latest_frame_callback = frame_provider
                    if voice_agent.start():
                        safe_console_info("语音管家麦克风初始化成功！等待唤醒...")
                    else:
                        safe_console_error("语音启动失败！(原因：未插入麦克风、或被占用)")

            # ★ 第二层循环：控制回退到“运行模式 / 节点选择”
            while _STATE["running"]:
                _STATE["connection_lost"] = False
                _STATE["video_running"] = False

                while not inference_queue.empty():
                    try:
                        inference_queue.get_nowait()
                    except:
                        pass

                if not select_run_mode(): break

                if _STATE["mode"] == "websocket":
                    pi_topology = get_lab_topology()
                    if not pi_topology: continue

                    manager = MultiPiManager(pi_topology)
                    threading.Thread(target=lambda: asyncio.run(manager.start()), daemon=True).start()

                    _STATE["video_running"] = True
                    safe_console_info(f"已启动多节点监控，共计 {len(pi_topology)} 个站点。按 ESC 退出监控。")
                    display_results = {pid: "" for pid in pi_topology.keys()}

                    try:
                        for pid in pi_topology.keys():
                            cv2.namedWindow(f"Node_{pid}", cv2.WINDOW_NORMAL)

                        # ★ 动态视频渲染循环
                        while _STATE["video_running"] and _STATE["running"]:
                            for pi_id in sorted(pi_topology.keys()):
                                frame = manager.frame_buffers.get(pi_id)
                                status = getattr(manager, 'node_status', {}).get(pi_id, "offline")

                                # 如果没有收到画面（正在连接或掉线），自动生成一块纯黑色的背景画布
                                if frame is None:
                                    img = np.zeros((480, 640, 3), dtype=np.uint8)
                                else:
                                    _STATE["frame_buffer"] = frame.copy()
                                    img = frame.copy()

                                res_text = display_results.get(pi_id, "")

                                # 在画面上动态打印该节点的当前状态
                                if status == "offline":
                                    img = draw_chinese_text(img, f"Node {pi_id}: 已断开, 正在尝试重连...", (20, 30),
                                                            text_color=(0, 0, 255))
                                elif status == "connecting":
                                    img = draw_chinese_text(img, f"Node {pi_id}: 正在连接网络...", (20, 30),
                                                            text_color=(0, 255, 255))
                                else:
                                    if res_text:
                                        img = draw_chinese_text(img, f"Node {pi_id}: {res_text}", (20, 30))

                                cv2.imshow(f"Node_{pi_id}", img)

                            key = cv2.waitKey(30) & 0xFF
                            if key == 27 or key == ord('q'):
                                _STATE["video_running"] = False
                                safe_console_info("用户主动按下退出键，结束当前监控。")
                                break

                            # ★ 智能断线回退判断：如果当前监控的【所有】节点都彻底断线，自动回退
                            all_offline = all(
                                getattr(manager, 'node_status', {}).get(pid) == "offline" for pid in pi_topology.keys())
                            if all_offline:
                                safe_console_info("所有节点均已断开，自动回退到网络配置...")
                                _STATE["connection_lost"] = True
                                _STATE["video_running"] = False
                                break

                    finally:
                        manager.stop()
                        cv2.destroyAllWindows()

                elif _STATE["mode"] == "camera":
                    cap = cv2.VideoCapture(0)
                    _STATE["video_running"] = True
                    while _STATE["video_running"] and _STATE["running"]:
                        ret, frame = cap.read()
                        if ret:
                            _STATE["frame_buffer"] = frame.copy()
                            res_text = latest_inference_result.get("text", "")
                            if res_text and time.time() - latest_inference_result.get("timestamp", 0) < 5:
                                frame = draw_chinese_text(frame, res_text, (20, 30))

                            cv2.imshow("Local Preview", frame)
                            try:
                                inference_queue.put_nowait(frame.copy())
                            except queue.Full:
                                pass

                        key = cv2.waitKey(30) & 0xFF
                        if key == 27 or key == ord('q'):
                            _STATE["video_running"] = False
                            break
                    cap.release()
                    cv2.destroyAllWindows()

                # ★ 异常状态分发判断
                if _STATE["connection_lost"] and _STATE["running"]:
                    time.sleep(1)
                    continue  # 继续第二层循环，回退到选模式/扫节点
                else:
                    break  # 跳出内层循环，回退到外层的模型选择

    except KeyboardInterrupt:
        print("\n[INFO] 接收到安全退出信号。")

    if voice_agent:
        voice_agent.stop()
    subprocess.run('taskkill /f /im ollama.exe >NUL 2>&1', shell=True)
    sys.stdout = getattr(sys.stdout, 'original_stream', sys.stdout)
    sys.stderr = getattr(sys.stderr, 'original_stream', sys.stderr)

    scheduler_manager.stop()  # 防止未定义退出
    export_log()


if __name__ == "__main__":
    main()