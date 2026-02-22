#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
main.py - 主程序入口
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
from typing import Optional

import requests
import websockets

# 尝试多种导入方式
try:
    # 尝试相对导入
    from core.config import get_config, set_config
    from core.logger import console_info, console_error, console_prompt
    from core.tts import speak_async
    from core.voice_interaction import get_voice_interaction, is_voice_interaction_available, VoiceInteractionConfig
    from core.ai_backend import list_ollama_models, analyze_image
    from communication.pcsend import setup_voice_sender, send_voice_result, cleanup_voice_sender
    from core.network import get_local_ip, get_network_prefix
except ImportError:
    try:
        # 尝试绝对导入
        from core.config import get_config, set_config
        from core.logger import console_info, console_error, console_prompt
        from core.tts import speak_async
        from core.voice_interaction import get_voice_interaction, is_voice_interaction_available, VoiceInteractionConfig
        from core.ai_backend import list_ollama_models, analyze_image
        from communication.pcsend import setup_voice_sender, send_voice_result, cleanup_voice_sender
        from core.network import get_local_ip, get_network_prefix
    except ImportError:
        try:
            # 尝试通过sys.path添加项目根目录
            current_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.dirname(current_dir)
            if project_root not in sys.path:
                sys.path.insert(0, project_root)

            from core.config import get_config, set_config
            from core.logger import console_info, console_error, console_prompt
            from core.tts import speak_async
            from core.voice_interaction import get_voice_interaction, is_voice_interaction_available, \
                VoiceInteractionConfig
            from core.ai_backend import list_ollama_models, analyze_image
            from communication.pcsend import setup_voice_sender, send_voice_result, cleanup_voice_sender
            from core.network import get_local_ip, get_network_prefix
        except ImportError:
            # 定义简单的替代函数（回退实现）
            def console_info(text: str):
                print(f"[INFO] {text}")


            def console_error(text: str):
                import time
                print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} [ERROR] {text}")


            def console_prompt(text: str):
                print(text)


            def speak_async(text: str):
                print(f"[SPEAK] {text}")


            def get_config(key_path: str, default=None):
                """模拟的get_config函数"""
                parts = key_path.split('.')
                if parts[0] == "camera" and parts[1] == "resolution" and parts[2] == "0":
                    return 1280
                elif parts[0] == "camera" and parts[1] == "resolution" and parts[2] == "1":
                    return 720
                elif parts[0] == "websocket" and parts[1] == "host":
                    return "192.168.31.31"
                elif parts[0] == "websocket" and parts[1] == "port":
                    return 8001
                elif parts[0] == "ws_retry" and parts[1] == "max_attempts":
                    return 5
                elif parts[0] == "ws_retry" and parts[1] == "interval":
                    return 3
                elif parts[0] == "ollama" and parts[1] == "default_models":
                    return ["llava:7b-v1.5-q4_K_M", "llava:13b-v1.5-q4_K_M", "llava:34b-v1.5-q4_K_M", "llava:latest"]
                return default


            def set_config(key_path: str, value):
                """模拟的set_config函数"""
                console_info(f"模拟设置配置: {key_path} = {value}")


            def list_ollama_models():
                """模拟的list_ollama_models函数"""
                return []


            def analyze_image(frame, model, backend):
                """模拟的analyze_image函数"""
                return "这是模拟的识别结果"


            def is_voice_interaction_available():
                """模拟的is_voice_interaction_available函数"""
                return False


            def get_voice_interaction(config):
                """模拟的get_voice_interaction函数"""

                class MockVoiceInteraction:
                    def __init__(self):
                        self.on_ai_response = None

                    def start(self):
                        return True

                    def set_ai_backend(self, backend, model, api_key):
                        pass

                return MockVoiceInteraction()


            def setup_voice_sender(auto_reconnect=True, connection_failed_callback=None,
                                   connection_established_callback=None):
                """模拟的setup_voice_sender函数"""

                class MockVoiceSender:
                    def is_connected(self):
                        return True

                return MockVoiceSender()


            def send_voice_result(text, priority=0):
                """模拟的send_voice_result函数"""
                console_info(f"模拟发送到树莓派: {text}")
                return True


            def cleanup_voice_sender():
                """模拟的cleanup_voice_sender函数"""
                pass


            def get_local_ip():
                """模拟的get_local_ip函数"""
                return "127.0.0.1"


            def get_network_prefix():
                """模拟的get_network_prefix函数"""
                return "192.168.31."

# 全局状态
_STATE = {
    "running": True,
    "mode": "",  # camera / websocket
    "frame_buffer": None,  # 稍后初始化
    "tts_available": False,
    "selected_model": "",
    "ai_backend": "",  # "ollama" or "qwen"
    "ws_connected": False,
    "ws_retry_attempts": 0  # WS重试次数
}


def is_admin():
    """检查是否以管理员权限运行"""
    try:
        # 尝试使用ctypes检查管理员权限
        return os.name != 'nt' or ctypes.windll.shell32.IsUserAnAdmin()
    except (AttributeError, NameError, OSError):
        # 如果ctypes不可用，假设不是管理员
        return False


def run_as_admin():
    """以管理员权限重新运行程序"""
    if os.name != 'nt':
        return False

    try:
        # 检查是否已经以管理员权限运行
        if is_admin():
            return True

        # 以管理员权限重新启动程序
        ctypes.windll.shell32.ShellExecuteW(
            None,
            "runas",
            sys.executable,
            " ".join(sys.argv),
            None,
            1
        )
        return True
    except Exception as e:
        console_error(f"无法以管理员权限运行: {str(e)}")
        return False


def check_dependencies():
    """检查并自动安装所有依赖包"""
    required_packages = ["cv2", "numpy", "requests", "websockets", "asyncio"]
    if is_voice_interaction_available():
        required_packages.extend(["speech_recognition", "pyaudio"])

    missing_pkgs = []
    for pkg in required_packages:
        try:
            __import__(pkg.split(".")[0])
        except ImportError:
            missing_pkgs.append(pkg.split(".")[0])

    if missing_pkgs:
        console_error(f"缺失依赖包: {', '.join(missing_pkgs)}")
        console_info("正在自动安装依赖...")
        try:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "-U"] + missing_pkgs,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            console_info("依赖包安装成功")
            return True
        except Exception as e:
            console_error(f"依赖安装失败: {str(e)[:50]}")
            return False

    # 检查Ollama
    if _STATE["ai_backend"] == "ollama":
        ollama_exe = "ollama.exe"
        default_path = "C:\\Users\\Administrator\\AppData\\Local\\Programs\\Ollama\\ollama.exe"
        if os.path.exists(default_path):
            ollama_exe = default_path
        if not os.path.exists(ollama_exe) and not subprocess.run("where ollama >NUL 2>&1", shell=True).returncode == 0:
            console_error("未检测到Ollama，请先安装Ollama（https://ollama.com/download/windows）")
            return False

    return True


def select_ai_backend():
    """选择AI后端：Ollama或Qwen"""
    console_prompt("\n===== AI后端选择 =====")
    console_prompt("1. Ollama (本地模型，如LLaVA)")
    console_prompt("2. Qwen3.5-Plus (云端模型，需API密钥)")

    while True:
        try:
            choice = input("\n请选择AI后端 (1 或 2): ").strip()
            if not choice.isdigit():
                console_error("请输入有效的数字")
                continue
            choice_idx = int(choice)
            if choice_idx == 1:
                _STATE["ai_backend"] = "ollama"
                console_info("已选择Ollama后端")
                return True
            elif choice_idx == 2:
                _STATE["ai_backend"] = "qwen"
                console_info("已选择Qwen3.5-Plus后端")
                return True
            else:
                console_error("请输入1或2")
        except Exception as e:
            console_error(f"输入无效，请重新选择: {str(e)}")
    return False


def select_model():
    """命令行交互选择模型（仅当使用Ollama时）"""
    if _STATE["ai_backend"] == "qwen":
        # 如果选择了Qwen，则不需要选择具体模型
        _STATE["selected_model"] = "qwen-vl-max"
        console_info("已选择Qwen-VL-Max模型")
        return True

    console_prompt("\n===== 模型选择 =====")
    local_models = list_ollama_models()
    all_models = list(set(get_config("ollama.default_models") + local_models))
    all_models.sort()
    console_prompt("可用模型列表（输入序号选择）：")
    for idx, model in enumerate(all_models, 1):
        status = "[已安装]" if model in local_models else "[未安装，将自动拉取]"
        console_prompt(f"{idx}. {model} {status}")
    console_prompt(f"{len(all_models) + 1}. 自定义模型")

    while True:
        try:
            choice = input("\n请输入模型序号: ").strip()
            if not choice.isdigit():
                console_error("请输入有效的数字序号")
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
                    console_error("模型名称不能为空")
            else:
                console_error(f"请输入1-{len(all_models) + 1}之间的数字")
        except Exception as e:
            console_error(f"输入无效，请重新选择: {str(e)}")

    console_info(f"已选择模型: {_STATE['selected_model']}")
    return True


def pull_ollama_model():
    """自动拉取选中的模型（不存在时，仅当使用Ollama时）"""
    if _STATE["ai_backend"] == "qwen":
        console_info("使用Qwen后端，跳过Ollama模型拉取")
        return True

    model = _STATE["selected_model"]
    if not model:
        console_error("未选择模型")
        return False

    local_models = list_ollama_models()
    if model in local_models:
        console_info(f"模型 {model} 已存在，无需拉取")
        return True

    console_info(f"\n开始拉取模型 {model}")
    console_info("=" * 50)

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
            console_info("=" * 50)
            console_info(f"模型 {model} 拉取成功")
            return True
        else:
            console_info("=" * 50)
            console_error(f"模型 {model} 拉取失败")
            return False
    except subprocess.TimeoutExpired:
        console_info("=" * 50)
        console_error("模型拉取超时（超过1小时）")
        return False
    except Exception as e:
        console_info("=" * 50)
        console_error(f"模型拉取异常: {str(e)[:50]}")
        return False


def start_ollama_service():
    """启动并验证Ollama服务（仅当使用Ollama时）"""
    if _STATE["ai_backend"] == "qwen":
        console_info("使用Qwen后端，跳过Ollama服务启动")
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
        console_error(f"Ollama启动失败: {str(e)[:50]}")
        return False

    for _ in range(15):
        try:
            if requests.get(f"{get_config('ollama.host')}/api/tags", timeout=1).status_code == 200:
                console_info("Ollama服务就绪")
                return True
        except Exception:
            time.sleep(1)
    console_info("Ollama连接超时，继续运行")
    return True


def select_run_mode():
    """选择运行模式：本机摄像头 / 树莓派WebSocket"""
    console_prompt("\n===== 运行模式选择 =====")
    console_prompt("1. 本机摄像头模式")
    console_prompt("2. 树莓派WebSocket模式")
    while True:
        try:
            choice = input("\n请输入模式序号: ").strip()
            if not choice.isdigit():
                console_error("请输入有效的数字序号")
                continue
            choice_idx = int(choice)
            if choice_idx == 1:
                _STATE["mode"] = "camera"
                console_info("已选择：本机摄像头模式")
                break
            elif choice_idx == 2:
                _STATE["mode"] = "websocket"
                # 使用配置中的树莓派IP
                pi_ip = get_config("network.pi_ip", "192.168.31.31")
                console_info(
                    f"已选择：树莓派WebSocket模式（地址：ws://{pi_ip}:{get_config('websocket.port')}）")
                break
            else:
                console_error("请输入1或2")
        except Exception as e:
            console_error(f"输入无效，请重新选择: {str(e)}")
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
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, get_config("camera.resolution.0"))
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, get_config("camera.resolution.1"))
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                console_info("本机摄像头初始化成功")
                break
        if cap and cap.isOpened():
            break

    while _STATE["running"] and _STATE["mode"] == "camera":
        if cap and cap.isOpened():
            try:
                ret, frame = cap.read()
                if ret:
                    _STATE["frame_buffer"] = frame.copy()
            except Exception as e:
                console_error(f"摄像头读取错误: {str(e)}")
                pass
        time.sleep(0.01)

    if cap:
        cap.release()


def _is_port_open(ip: str, port: int) -> bool:
    """
    检查端口是否开放
    Args:
        ip: IP地址
        port: 端口号
    Returns:
        bool: 端口是否开放
    """
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.5)
        result = sock.connect_ex((ip, port))
        sock.close()
        return result == 0
    except Exception:
        return False


def discover_raspberry_pi() -> Optional[str]:
    """
    搜索网络中的树莓派
    Returns:
        Optional[str]: 找到的树莓派IP地址，如果未找到返回None
    """
    console_info("正在搜索网络中的树莓派...")

    # 尝试从配置获取已知的树莓派IP
    known_pi_ip = get_config("network.pi_ip")
    if known_pi_ip and known_pi_ip != "192.168.31.31" and not known_pi_ip.startswith("127."):
        console_info(f"尝试连接已知树莓派地址: {known_pi_ip}")
        if _is_port_open(known_pi_ip, 8001):
            console_info(f"成功连接到树莓派: {known_pi_ip}")
            return known_pi_ip

    # 如果已知IP不可用，进行网络搜索
    try:
        # 获取本机IP和网络前缀
        local_ip = get_local_ip()
        network_prefix = get_network_prefix()

        console_info(f"扫描网络段: {network_prefix}x")

        # 扫描整个子网
        for i in range(1, 255):
            ip = f"{network_prefix}{i}"
            # 跳过本机IP和回环地址
            if ip == local_ip or ip.startswith("127."):
                continue

            # 检查8001端口是否开放
            if _is_port_open(ip, 8001):
                console_info(f"在 {ip} 上发现开放端口 8001")
                # 额外验证 - 检查是否是我们的树莓派服务
                try:
                    response = requests.get(f"http://{ip}:8001", timeout=2)
                    if "树莓派视频流服务器" in response.text or "WebSocket服务器" in response.text:
                        console_info(f"确认发现树莓派: {ip}")
                        # 保存到配置
                        set_config("network.pi_ip", ip)
                        return ip
                except Exception:
                    continue

        console_info("未发现树莓派")
        return None
    except Exception as e:
        console_error(f"网络搜索异常: {str(e)}")
        return None


def setup_network():
    """设置网络配置"""
    console_prompt("\n===== 网络配置 =====")

    # 获取本机IP并保存
    local_ip = get_local_ip()
    console_info(f"本机IP地址: {local_ip}")
    set_config("network.local_ip", local_ip)

    # 尝试发现树莓派
    pi_ip = discover_raspberry_pi()

    if pi_ip:
        console_info(f"已自动设置树莓派IP: {pi_ip}")
        # 更新WebSocket配置
        set_config("websocket.host", pi_ip)
    else:
        # 手动配置
        pi_ip = input("[INFO]请输入树莓派IP地址: ").strip()
        if pi_ip:
            set_config("network.pi_ip", pi_ip)
            set_config("websocket.host", pi_ip)
            console_info(f"已设置树莓派地址为: {pi_ip}")
        else:
            console_info("未设置树莓派地址，将使用默认地址")


async def websocket_client():
    """WebSocket客户端：接收树莓派视频流（含重试逻辑）"""
    # 使用配置中的树莓派IP
    pi_ip = get_config("network.pi_ip", "192.168.31.31")
    uri = f"ws://{pi_ip}:{get_config('websocket.port')}"
    console_info(f"正在连接树莓派WebSocket服务器：{uri}")

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
                console_info("树莓派WebSocket连接成功，开始接收视频流...")
                speak_async("树莓派连接成功，开始接收视频流")

                while _STATE["running"] and _STATE["mode"] == "websocket":
                    try:
                        frame_data = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                        np_arr = np.frombuffer(frame_data, np.uint8)
                        frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
                        if frame is not None and frame.size > 0:
                            frame = cv2.resize(frame,
                                               (get_config("camera.resolution.0"), get_config("camera.resolution.1")))
                            _STATE["frame_buffer"] = frame.copy()
                    except asyncio.TimeoutError:
                        continue
                    except websockets.exceptions.ConnectionClosed:
                        console_error("树莓派WebSocket连接断开")
                        _STATE["ws_connected"] = False
                        speak_async("树莓派连接断开")
                        break
                    except Exception as e:
                        console_error(f"WebSocket接收异常: {str(e)[:50]}")
                        continue
        except OSError as e:
            _STATE["ws_retry_attempts"] += 1
            console_error(f"第{_STATE['ws_retry_attempts']}次连接失败: {str(e)[:50]}")
            # 判断是否达到最大重试次数
            if _STATE["ws_retry_attempts"] >= get_config("ws_retry.max_attempts"):
                console_info(f"已达到最大重试次数({get_config('ws_retry.max_attempts')})，继续尝试连接")
                # 尝试重新搜索树莓派
                pi_ip = discover_raspberry_pi()
                if pi_ip:
                    console_info(f"发现树莓派: {pi_ip}")
                    # 更新WebSocket配置
                    set_config("network.pi_ip", pi_ip)
                    set_config("websocket.host", pi_ip)
                    # 重置重试次数
                    _STATE["ws_retry_attempts"] = 0
                else:
                    # 继续尝试连接，不要退出
                    console_info("未发现树莓派，继续尝试连接...")
            else:
                # 未达最大次数，自动重试
                retry_interval = get_config("ws_retry.interval")
                console_info(
                    f"{retry_interval}秒后自动重试（剩余{get_config('ws_retry.max_attempts') - _STATE['ws_retry_attempts']}次）")
                await asyncio.sleep(retry_interval)
        except Exception as e:
            _STATE["ws_retry_attempts"] += 1
            console_error(f"第{_STATE['ws_retry_attempts']}次连接失败: {str(e)[:50]}")
            # 继续尝试连接，不要退出
            retry_interval = get_config("ws_retry.interval")
            await asyncio.sleep(retry_interval)


def start_websocket_worker():
    """启动WebSocket客户端线程"""

    def _run_ws():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(websocket_client())
        except Exception as e:
            console_error(f"WebSocket客户端错误: {str(e)}")
        finally:
            try:
                loop.close()
            except Exception:
                pass

    ws_thread = threading.Thread(target=_run_ws, daemon=True)
    ws_thread.start()
    time.sleep(2)


def setup_voice_interaction():
    """设置语音交互功能"""
    if not is_voice_interaction_available():
        console_info("语音交互功能不可用，需要安装speech_recognition和pyaudio")
        return False

    console_prompt("\n===== 语音交互配置 =====")
    choice = input("是否启用语音交互功能? (y/N): ").strip().lower()
    if choice not in ('y', 'yes'):
        console_info("语音交互功能已禁用")
        return False

    config = VoiceInteractionConfig()

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

    # 创建语音交互实例
    voice_interaction = get_voice_interaction(config)

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
                console_info("切换到树莓派WebSocket模式")
                # 启动WebSocket客户端
                threading.Thread(target=start_websocket_worker, daemon=True).start()
            else:
                _STATE["mode"] = "camera"
                console_info("切换到本机摄像头模式")
                # 启动摄像头线程
                threading.Thread(target=camera_worker, daemon=True).start()

    voice_interaction.on_ai_response = on_ai_response

    # 启动语音交互
    if voice_interaction.start():
        console_info("语音交互功能已启用")
        return True
    else:
        console_info("语音交互功能启动失败")
        return False


def setup_pcsend():
    """设置pcsend服务"""
    if _STATE["mode"] == "websocket":
        # 设置连接失败和建立的回调
        def pi_connection_failed_callback(error_info: dict):
            console_error(f"树莓派连接失败: {error_info.get('error', '未知错误')}")

        def pi_connection_established_callback(conn_info: dict):
            console_info(f"成功连接到树莓派，已运行{conn_info['uptime']:.1f}秒")

        setup_voice_sender(
            auto_reconnect=True,
            connection_failed_callback=pi_connection_failed_callback,
            connection_established_callback=pi_connection_established_callback
        )
        console_info("WebSocket模式下自动启用向树莓派发送输出文本")


def infer_frame():
    """图像推理（根据选择的后端）"""
    try:
        result = analyze_image(
            _STATE["frame_buffer"],
            _STATE["selected_model"],
            _STATE["ai_backend"]
        )
        # 识别结果属于 VOICE 输出
        if _STATE["mode"] == "websocket":
            # 在websocket模式下，发送到树莓派
            if send_voice_result(result):
                console_info(f"已发送到树莓派: {result}")
            else:
                console_error(f"发送到树莓派失败: {result}")
        else:
            # 在本机摄像头模式下，本地播报
            speak_async(result)
    except Exception as e:
        error_msg = f"{_STATE['ai_backend'].capitalize()}识别失败: {str(e)[:50]}"
        console_error(error_msg)
        if _STATE["mode"] == "websocket":
            send_voice_result("识别失败")
        else:
            speak_async("识别失败")


def main():
    """主程序入口"""

    # 添加信号处理，捕获Ctrl+C
    def signal_handler(sig, frame):
        console_info("用户退出")
        _STATE["running"] = False
        # 清理资源
        try:
            subprocess.run('taskkill /f /im ollama.exe >NUL 2>&1', shell=True)
        except Exception as e:
            console_error(f"清理Ollama服务失败: {str(e)}")
        # 退出消息
        speak_async("系统已退出")
        # 清理 pcsend 资源
        try:
            cleanup_voice_sender()
        except Exception as e:
            console_error(f"清理pcsend资源失败: {str(e)}")
        console_prompt("\n系统正常退出")
        sys.exit(0)

    # 注册信号处理
    signal.signal(signal.SIGINT, signal_handler)

    # 仅在Windows系统下检查管理员权限
    if os.name == 'nt':
        if not is_admin():
            if run_as_admin():
                return
            else:
                console_error("无法以管理员权限运行，某些功能可能受限")

    # 获取摄像头分辨率，确保是整数
    try:
        width = int(get_config("camera.resolution.0", 1280))
        height = int(get_config("camera.resolution.1", 720))
    except (TypeError, ValueError):
        width = 1280
        height = 720

    # 初始化 frame_buffer
    _STATE["frame_buffer"] = np.zeros((height, width, 3), np.uint8)

    console_prompt("=" * 60)
    console_prompt("实时视频分析系统 - 树莓派/PC双模式版")
    console_prompt("=" * 60)

    if not check_dependencies():
        input("\n按回车退出...")
        return

    # 设置网络配置
    setup_network()

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

    # 询问是否启用语音交互功能
    try:
        if is_voice_interaction_available():
            if setup_voice_interaction():
                console_info("语音交互功能已启用")
    except Exception as e:
        console_info(f"语音交互功能初始化失败: {str(e)}")

    # 设置pcsend
    setup_pcsend()

    # 启动提示
    backend_name = "Qwen3.5-Plus" if _STATE["ai_backend"] == "qwen" else _STATE["selected_model"]
    if _STATE["mode"] == "websocket":
        speak_async(f"系统已启动，websocket模式，使用{backend_name}进行分析")
    else:
        speak_async(f"系统已启动，本机摄像头模式，使用{backend_name}进行分析")

    if _STATE["mode"] == "camera":
        threading.Thread(target=camera_worker, daemon=True).start()
    elif _STATE["mode"] == "websocket":
        start_websocket_worker()

    cv2.namedWindow("Video Analysis (Raspberry Pi/PC)", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("Video Analysis (Raspberry Pi/PC)", get_config("display.width"), get_config("display.height"))

    last_infer = 0
    try:
        while _STATE["running"]:
            current = time.time()
            if current - last_infer >= get_config("inference.interval") and not np.all(_STATE["frame_buffer"] == 0):
                infer_frame()
                last_infer = current

            cv2.imshow("Video Analysis (Raspberry Pi/PC)", _STATE["frame_buffer"])
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                _STATE["running"] = False
                break
            elif key == ord('m'):
                console_prompt("\n===== 切换运行模式 =====")
                select_run_mode()
                if _STATE["mode"] == "camera":
                    threading.Thread(target=camera_worker, daemon=True).start()
                elif _STATE["mode"] == "websocket":
                    start_websocket_worker()

        cv2.destroyAllWindows()
        try:
            subprocess.run('taskkill /f /im ollama.exe >NUL 2>&1', shell=True)
        except Exception as e:
            console_error(f"清理Ollama服务失败: {str(e)}")

        # 退出消息
        speak_async("系统已退出")

        # 清理 pcsend 资源
        try:
            cleanup_voice_sender()
        except Exception as e:
            console_error(f"清理pcsend资源失败: {str(e)}")

        console_prompt("\n系统正常退出")
    except KeyboardInterrupt:
        console_info("用户退出")
        # 正常清理资源
        cv2.destroyAllWindows()
        try:
            subprocess.run('taskkill /f /im ollama.exe >NUL 2>&1', shell=True)
        except Exception as e:
            console_error(f"清理Ollama服务失败: {str(e)}")
        speak_async("系统已退出")
        try:
            cleanup_voice_sender()
        except Exception as e:
            console_error(f"清理pcsend资源失败: {str(e)}")
        console_prompt("\n系统正常退出")


if __name__ == "__main__":
    main()