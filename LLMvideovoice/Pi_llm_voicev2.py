#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
实时视频分析系统 - 树莓派/PC双模式版
新增：PyTorch/Python版本检测，精准提示版本适配方案
"""
import sys
import platform
import subprocess
import ctypes
import ctypes.wintypes


# 先执行版本检测，再导入其他依赖
# ====================== 版本检测核心逻辑 ======================
def check_python_version():
    """检查Python版本，提示回退到3.11"""
    py_ver = sys.version_info
    current_ver = f"{py_ver.major}.{py_ver.minor}.{py_ver.micro}"
    target_ver = (3, 11)

    # 定义兼容范围：仅3.11为最优，其他版本提示回退
    if py_ver[:2] != target_ver:
        warning_msg = f"""
⚠️ Python版本兼容性警告 ⚠️
当前Python版本：{current_ver}
推荐版本：Python 3.11.x
检测到版本不兼容风险，请回退到Python 3.11以避免运行错误！
"""
        print(warning_msg)
        # 可选：暂停让用户看到提示
        input("按回车键继续（建议先安装Python 3.11）...")


def check_torch_version():
    """检查PyTorch版本，要求≥2.11.0.dev20260210+cu128"""
    required_torch_ver = "2.11.0.dev20260210+cu128"

    try:
        import torch
        current_torch_ver = torch.__version__

        # 版本解析：处理开发版+CUDA后缀的对比
        def parse_torch_version(ver_str):
            """解析PyTorch版本字符串为可比较的元组"""
            # 拆分开发版/正式版 + CUDA后缀
            ver_part = ver_str.split('+')[0]
            # 拆分主版本.次版本.修订版
            ver_parts = ver_part.replace('dev', '.dev.').split('.')

            # 转换为可比较的元组（数字部分转int，字符串保留）
            parsed = []
            for part in ver_parts:
                if part.isdigit():
                    parsed.append(int(part))
                else:
                    parsed.append(part)
            return tuple(parsed)

        current_parsed = parse_torch_version(current_torch_ver)
        required_parsed = parse_torch_version(required_torch_ver)

        # 版本对比
        if current_parsed < required_parsed:
            error_msg = f"""
❌ PyTorch版本过低 ❌
当前版本：{current_torch_ver}
要求版本：≥ {required_torch_ver}
请安装指定版本的PyTorch：
pip install torch==2.11.0.dev20260210+cu128 -f https://download.pytorch.org/whl/nightly/cu128/torch_nightly.html
"""
            print(error_msg)
            # 可选：提供自动安装选项
            choice = input("是否自动安装符合要求的PyTorch版本？(y/n)：").strip().lower()
            if choice == 'y':
                install_cmd = [
                    sys.executable, "-m", "pip", "install",
                    "torch==2.11.0.dev20260210+cu128",
                    "-f", "https://download.pytorch.org/whl/nightly/cu128/torch_nightly.html"
                ]
                try:
                    subprocess.check_call(install_cmd)
                    print("✅ PyTorch安装成功，请重启程序！")
                    sys.exit(0)
                except subprocess.CalledProcessError:
                    print("❌ 自动安装失败，请手动执行上述命令！")
                    sys.exit(1)
            else:
                sys.exit(1)
        else:
            print(f"✅ PyTorch版本符合要求：{current_torch_ver}")

    except ImportError:
        # 未安装PyTorch的情况
        error_msg = f"""
❌ 未检测到PyTorch ❌
要求安装版本：≥ {required_torch_ver}
请先安装指定版本的PyTorch：
pip install torch==2.11.0.dev20260210+cu128 -f https://download.pytorch.org/whl/nightly/cu128/torch_nightly.html
"""
        print(error_msg)
        choice = input("是否自动安装？(y/n)：").strip().lower()
        if choice == 'y':
            install_cmd = [
                sys.executable, "-m", "pip", "install",
                "torch==2.11.0.dev20260210+cu128",
                "-f", "https://download.pytorch.org/whl/nightly/cu128/torch_nightly.html"
            ]
            try:
                subprocess.check_call(install_cmd)
                print("✅ PyTorch安装成功，请重启程序！")
                sys.exit(0)
            except subprocess.CalledProcessError:
                print("❌ 自动安装失败，请手动执行上述命令！")
                sys.exit(1)
        else:
            sys.exit(1)


# 执行版本检测（程序启动时优先执行）
print("=" * 60)
print("📋 开始版本兼容性检测...")
check_python_version()
check_torch_version()
print("✅ 版本检测通过，启动系统...")
print("=" * 60)

# ====================== 原有代码（以下保持不变） ======================
import asyncio
import websockets
import cv2
import numpy as np
import threading
import base64
import binascii
import requests
import os
import time
import locale


# ====================== 编码修复 ======================
def fix_console_encoding():
    """修复Windows控制台编码，解决中文乱码"""
    if platform.system() == "Windows":
        try:
            sys.stdout.reconfigure(encoding='utf-8')
            sys.stderr.reconfigure(encoding='utf-8')

            kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel32.SetConsoleOutputCP(65001)
            kernel32.SetConsoleCP(65001)

            locale.setlocale(locale.LC_ALL, 'zh_CN.UTF-8')
        except (AttributeError, OSError):
            os.environ['PYTHONIOENCODING'] = 'utf-8'
            os.system('chcp 65001 >nul 2>&1')


fix_console_encoding()

# ====================== 类型定义 & 全局配置 ======================
ConfigType = dict[str, int | str | tuple[int, int] | dict[str, object] | list[str]]
StateType = dict[str, bool | str | np.ndarray | object | int | asyncio.AbstractEventLoop | asyncio.Task]

CONFIG: ConfigType = {
    "camera": {"index": 0, "resolution": (1280, 720)},
    "ollama": {
        "host": "http://localhost:11434",
        "default_models": ["llava:7b-v1.5-q4_K_M", "llava:13b-v1.5-q4_K_M", "llava:34b-v1.5-q4_K_M", "llava:latest"]
    },
    "inference": {"interval": 5.0, "timeout": 20.0},
    "gpu": {"layers": 35},
    "websocket": {"host": "192.168.31.31", "port": 8001},
    "display": {"width": 1280, "height": 720},
    "ws_retry": {"max_attempts": 5, "interval": 3.0},
    "exit_keys": [ord('q'), ord('Q'), 27],
    "tts_enabled": True
}

FRAME_HEIGHT: int = CONFIG["camera"]["resolution"][1]  # type: ignore
FRAME_WIDTH: int = CONFIG["camera"]["resolution"][0]  # type: ignore
_STATE: StateType = {
    "running": True,
    "mode": "",
    "frame_buffer": np.zeros((FRAME_HEIGHT, FRAME_WIDTH, 3), np.uint8),
    "tts_speaker": None,
    "selected_model": "",
    "ws_connected": False,
    "ws_loop": None,
    "ws_task": None,
    "ws_retry_attempts": 0
}


# ====================== 通用工具方法 ======================
class SystemUtils:
    """系统通用工具类"""

    @staticmethod
    def is_windows() -> bool:
        """判断是否为Windows系统"""
        return platform.system() == "Windows"

    @staticmethod
    def is_admin() -> bool:
        """检查是否为管理员权限"""
        if not SystemUtils.is_windows():
            return True
        try:
            shell32 = ctypes.WinDLL("shell32.dll", use_last_error=True)
            shell32.IsUserAnAdmin.restype = ctypes.wintypes.BOOL
            return bool(shell32.IsUserAnAdmin())
        except (AttributeError, OSError) as admin_err:
            print(f"[WARNING] 管理员权限检查失败: {str(admin_err)[:30]}")
            return False

    @staticmethod
    def run_as_admin(file_path: str) -> None:
        """以管理员身份运行程序"""
        if not SystemUtils.is_windows():
            return
        sw_show_normal = 1
        try:
            shell32 = ctypes.WinDLL("shell32.dll", use_last_error=True)
            shell32.ShellExecuteW.restype = ctypes.wintypes.HINSTANCE
            shell32.ShellExecuteW.argtypes = [  # type: ignore
                ctypes.wintypes.HWND, ctypes.c_wchar_p, ctypes.c_wchar_p,
                ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.wintypes.INT
            ]
            shell32.ShellExecuteW(None, "runas", sys.executable, file_path, None, sw_show_normal)
        except (AttributeError, OSError) as run_err:
            print(f"[WARNING] 管理员权限提升失败: {str(run_err)[:30]}")

    @staticmethod
    def execute_command(cmd: list[str], timeout: float = 30.0, capture_output: bool = False) -> tuple[bool, str | None]:
        """通用命令执行方法（完全屏蔽ollama进程的英文提示，仅显示中文）"""
        try:
            kwargs = {
                "timeout": timeout,
                "shell": SystemUtils.is_windows(),
                "encoding": 'utf-8' if capture_output else None,
                "errors": 'ignore' if capture_output else None,
                "stdout": subprocess.DEVNULL,  # 屏蔽所有标准输出
                "stderr": subprocess.DEVNULL  # 屏蔽所有错误输出
            }

            # 执行命令（不捕获原始输出，避免显示英文提示）
            result = subprocess.run(cmd, **kwargs)  # type: ignore

            # 仅针对ollama进程操作，手动输出中文提示
            if "taskkill" in cmd and "ollama.exe" in cmd:
                if result.returncode == 0:
                    print("成功：ollama.exe进程已终止。")
                else:
                    print("[INFO] 当前无运行中的ollama.exe进程，无需终止。")

            return result.returncode == 0, None
        except subprocess.TimeoutExpired as cmd_timeout_err:
            return False, f"[WARNING] 命令执行超时: {str(cmd_timeout_err)[:20]}"
        except subprocess.SubprocessError as cmd_err:
            return False, f"[ERROR] 命令执行失败: {str(cmd_err)[:30]}"

    @staticmethod
    def http_request(method: str, url: str, json_data: dict | None = None,
                     timeout: float = 10.0, retries: int = 2) -> requests.Response | None:
        """通用HTTP请求方法"""
        for attempt in range(retries):
            try:
                if method.upper() == "GET":
                    resp = requests.get(url, timeout=timeout)
                elif method.upper() == "POST":
                    resp = requests.post(url, json=json_data, timeout=timeout)
                else:
                    return None

                if resp.status_code == 200:
                    return resp
                elif attempt < retries - 1:
                    time.sleep(1.0)
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as req_err:
                if attempt < retries - 1:
                    time.sleep(1.0)
                    continue
                print(f"[WARNING] HTTP请求失败: {str(req_err)[:30]}")
        return None

    @staticmethod
    def input_choice(prompt: str, min_val: int, max_val: int) -> int | None:
        """通用输入选择方法（保持中文交互）"""
        while True:
            try:
                choice_input = input(prompt).strip()
                if not choice_input.isdigit():
                    print("请输入有效的数字序号")
                    continue
                choice = int(choice_input)
                if min_val <= choice <= max_val:
                    return choice
                print(f"请输入{min_val}-{max_val}之间的数字")
            except (ValueError, EOFError, KeyboardInterrupt) as input_err:
                print(f"\n[INFO] 用户取消输入: {str(input_err)[:20]}")
                return None


# ====================== Ollama管理类 ======================
class OllamaManager:
    """Ollama服务管理类"""

    @staticmethod
    def get_ollama_path() -> str:
        """获取Ollama可执行文件路径"""
        if SystemUtils.is_windows():
            default_path = "C:\\Users\\Administrator\\AppData\\Local\\Programs\\Ollama\\ollama.exe"
            return default_path if os.path.exists(default_path) else "ollama.exe"
        return "ollama"

    @staticmethod
    def stop_service() -> None:
        """停止Ollama服务"""
        if SystemUtils.is_windows():
            SystemUtils.execute_command(["taskkill", "/f", "/im", "ollama.exe"], timeout=5.0)
        else:
            SystemUtils.execute_command(["pkill", "ollama"], timeout=5.0)
        time.sleep(0.5)

    @staticmethod
    def list_models() -> list[str]:
        """获取本地已安装的Ollama模型列表"""
        local_models = []
        ollama_exe = OllamaManager.get_ollama_path()

        serve_process = None
        try:
            serve_process = subprocess.Popen(
                [ollama_exe, "serve"],
                creationflags=subprocess.CREATE_NEW_CONSOLE if SystemUtils.is_windows() else 0,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            time.sleep(3.0)

            resp = SystemUtils.http_request("GET", f"{CONFIG['ollama']['host']}/api/tags", retries=3)
            if resp:
                models_data = resp.json().get("models", [])
                local_models = [str(m.get("name", "")) for m in models_data if
                                "llava" in str(m.get("name", "")).lower()]
        except subprocess.SubprocessError as serve_err:
            print(f"[WARNING] 启动临时Ollama服务失败: {str(serve_err)[:30]}")
        finally:
            if serve_process:
                try:
                    serve_process.terminate()
                except Exception as term_err:
                    print(f"[WARNING] 终止临时服务失败: {str(term_err)[:20]}")
            OllamaManager.stop_service()
        return local_models

    @staticmethod
    def select_model() -> bool:
        """选择模型（保持中文交互）"""
        print("\n===== 模型选择 =====")
        local_models = OllamaManager.list_models()
        default_models_list: list[str] = CONFIG["ollama"]["default_models"]  # type: ignore
        all_models = sorted(list(set(default_models_list + local_models)))

        print("可用模型列表（输入序号选择）：")
        for idx, model in enumerate(all_models, 1):
            status = "[已安装]" if model in local_models else "[未安装，将自动拉取]"
            print(f"{idx}. {model} {status}")
        print(f"{len(all_models) + 1}. 自定义模型")

        choice = SystemUtils.input_choice("\n请输入模型序号: ", 1, len(all_models) + 1)
        if not choice:
            return False

        if 1 <= choice <= len(all_models):
            _STATE["selected_model"] = str(all_models[choice - 1])
        else:
            custom_model = input("请输入自定义模型名称（如llava:7b）: ").strip()
            if not custom_model:
                print("模型名称不能为空")
                return False
            _STATE["selected_model"] = custom_model

        print(f"\n[INFO] 已选择模型: {_STATE['selected_model']}")
        return True

    @staticmethod
    def pull_model() -> bool:
        """拉取模型"""
        model_name = str(_STATE["selected_model"]).strip()
        if not model_name:
            print("[ERROR] 未选择模型")
            return False

        if model_name in OllamaManager.list_models():
            print(f"[INFO] 模型 {model_name} 已存在，无需拉取")
            return True

        OllamaManager.stop_service()
        print(f"\n[INFO] 开始拉取模型 {model_name}\n{'=' * 50}")

        # 拉取模型时需要显示输出，单独处理
        ollama_exe = OllamaManager.get_ollama_path()
        try:
            pull_proc = subprocess.Popen(
                [ollama_exe, "pull", model_name],
                shell=True,
                stdout=sys.stdout,
                stderr=sys.stderr,
                creationflags=subprocess.CREATE_NEW_CONSOLE if SystemUtils.is_windows() else 0
            )
            pull_proc.wait(timeout=3600)

            if pull_proc.returncode == 0:
                print("=" * 50)
                print(f"[INFO] 模型 {model_name} 拉取成功")
                return True
            else:
                print("=" * 50)
                print(f"[ERROR] 模型 {model_name} 拉取失败")
                return False
        except subprocess.TimeoutExpired:
            print("=" * 50)
            print("[ERROR] 模型拉取超时（超过1小时）")
            return False
        except Exception as e:
            print("=" * 50)
            print(f"[ERROR] 模型拉取异常: {str(e)[:50]}")
            return False

    @staticmethod
    def start_service() -> bool:
        """启动Ollama服务"""
        OllamaManager.stop_service()
        ollama_exe = OllamaManager.get_ollama_path()

        try:
            os.environ["OLLAMA_HOST"] = "127.0.0.1:11434"
            subprocess.Popen(
                [ollama_exe, "serve"],
                creationflags=subprocess.CREATE_NEW_CONSOLE if SystemUtils.is_windows() else 0,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        except subprocess.SubprocessError as start_err:
            print(f"[ERROR] Ollama启动失败: {str(start_err)[:50]}")
            return False

        service_ready = False
        for _ in range(20):
            if SystemUtils.http_request("GET", f"{CONFIG['ollama']['host']}/api/tags", timeout=1.0):
                service_ready = True
                break
            time.sleep(1.0)

        if service_ready:
            print("[INFO] Ollama服务就绪")
            return True
        print("[WARNING] Ollama连接超时，继续运行")
        return True


# ====================== 视频处理类 ======================
class VideoProcessor:
    """视频处理类"""

    @staticmethod
    def init_camera() -> cv2.VideoCapture | None:
        """初始化摄像头"""
        camera_cap = None
        indexes = [0, 1]
        apis = [cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY] if SystemUtils.is_windows() else [cv2.CAP_V4L2, cv2.CAP_ANY]

        for idx in indexes:
            for api in apis:
                try:
                    camera_cap = cv2.VideoCapture(idx, api)
                    if camera_cap.isOpened():
                        camera_cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
                        camera_cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
                        camera_cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                        print(f"[INFO] 本机摄像头初始化成功（索引：{idx}）")
                        return camera_cap
                except cv2.error as cv_err:
                    if camera_cap:
                        camera_cap.release()
                    camera_cap = None
                    print(f"[WARNING] 摄像头初始化失败（索引{idx}）: {str(cv_err)[:30]}")
                    continue

        print("[ERROR] 本机摄像头初始化失败")
        return camera_cap

    @staticmethod
    def camera_worker() -> None:
        """摄像头采集线程"""
        camera_cap = VideoProcessor.init_camera()
        if not camera_cap:
            return

        while _STATE["running"] and _STATE["mode"] == "camera":
            try:
                ret, frame = camera_cap.read()
                if ret and frame is not None and frame.size > 0:
                    _STATE["frame_buffer"] = frame.copy()
                time.sleep(0.01)
            except cv2.error as read_err:
                print(f"[WARNING] 摄像头读取异常: {str(read_err)[:30]}")
                time.sleep(0.1)

        camera_cap.release()
        print("[INFO] 摄像头采集线程已停止")

    @staticmethod
    async def websocket_client() -> None:
        """WebSocket客户端"""
        ws_host = CONFIG["websocket"]["host"]  # type: ignore
        ws_port = CONFIG["websocket"]["port"]  # type: ignore
        uri = f'ws://{ws_host}:{ws_port}'
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
                    _STATE["ws_retry_attempts"] = 0
                    print("[INFO] 树莓派WebSocket连接成功")
                    TTSManager.speak("树莓派连接成功，开始接收视频流")

                    while _STATE["running"] and _STATE["mode"] == "websocket":
                        try:
                            frame_data = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                            frame_np = np.frombuffer(bytes(frame_data), np.uint8)
                            frame = cv2.imdecode(frame_np, cv2.IMREAD_COLOR)
                            if frame is not None and frame.size > 0:
                                _STATE["frame_buffer"] = cv2.resize(frame, (FRAME_WIDTH, FRAME_HEIGHT))
                        except asyncio.TimeoutError:
                            continue
                        except websockets.exceptions.ConnectionClosed as ws_close_err:
                            print(f"[ERROR] WebSocket连接断开: {str(ws_close_err)[:30]}")
                            _STATE["ws_connected"] = False
                            TTSManager.speak("树莓派连接断开")
                            break
            except websockets.exceptions.WebSocketException as ws_err:
                _STATE["ws_retry_attempts"] += 1
                print(f"[ERROR] 第{_STATE['ws_retry_attempts']}次连接失败: {str(ws_err)[:50]}")

                max_attempts = CONFIG["ws_retry"]["max_attempts"]  # type: ignore
                if _STATE["ws_retry_attempts"] >= max_attempts:
                    choice = VideoProcessor.ws_connection_failed_choice()
                    if choice == "retry":
                        _STATE["ws_retry_attempts"] = 0
                    elif choice == "switch_camera":
                        threading.Thread(target=VideoProcessor.camera_worker, daemon=True).start()
                        break
                    elif choice == "exit":
                        break
                else:
                    retry_interval = CONFIG["ws_retry"]["interval"]  # type: ignore
                    remaining = max_attempts - _STATE["ws_retry_attempts"]
                    print(f"[INFO] {retry_interval}秒后自动重试（剩余{remaining}次）")
                    time.sleep(retry_interval)

    @staticmethod
    def ws_connection_failed_choice() -> str:
        """WebSocket连接失败时的用户选择（保持中文交互）"""
        print("\n===== 连接失败选择 =====")
        max_attempts = CONFIG["ws_retry"]["max_attempts"]  # type: ignore
        remaining = max_attempts - _STATE["ws_retry_attempts"]
        print(f"1. 继续重试连接树莓派（最多剩余{remaining}次）")
        print("2. 切换到本机摄像头模式运行")
        print("3. 正常退出程序")

        choice = SystemUtils.input_choice("\n请输入选择序号: ", 1, 3)
        if choice == 1:
            retry_interval = CONFIG["ws_retry"]["interval"]  # type: ignore
            time.sleep(retry_interval)
            return "retry"
        elif choice == 2:
            _STATE["mode"] = "camera"
            print("[INFO] 切换到本机摄像头模式")
            TTSManager.speak("树莓派连接失败，切换到本机摄像头模式")
            return "switch_camera"
        else:
            _STATE["running"] = False
            print("[INFO] 正在退出程序...")
            TTSManager.speak("程序已退出")
            return "exit"

    @staticmethod
    def start_websocket_worker() -> None:
        """启动WebSocket线程"""

        def _run_ws():
            _STATE["ws_loop"] = asyncio.new_event_loop()
            asyncio.set_event_loop(_STATE["ws_loop"])
            _STATE["ws_task"] = _STATE["ws_loop"].create_task(VideoProcessor.websocket_client())
            try:
                _STATE["ws_loop"].run_until_complete(_STATE["ws_task"])
            except (asyncio.exceptions.CancelledError, RuntimeError) as loop_err:
                print(f"[WARNING] WebSocket循环异常: {str(loop_err)[:30]}")

        threading.Thread(target=_run_ws, daemon=True).start()
        time.sleep(2.0)

    @staticmethod
    def select_run_mode() -> bool:
        """选择运行模式（保持中文交互）"""
        print("\n===== 运行模式选择 =====")
        print("1. 本机摄像头模式")
        print("2. 树莓派WebSocket模式")

        choice = SystemUtils.input_choice("\n请输入模式序号: ", 1, 2)
        if not choice:
            return False

        if choice == 1:
            _STATE["mode"] = "camera"
            print("\n[INFO] 已选择：本机摄像头模式")
        else:
            _STATE["mode"] = "websocket"
            ws_host = CONFIG["websocket"]["host"]  # type: ignore
            ws_port = CONFIG["websocket"]["port"]  # type: ignore
            mode_info = f"树莓派WebSocket模式（地址：ws://{ws_host}:{ws_port}）"
            print(f"\n[INFO] 已选择：{mode_info}")
        return True

    @staticmethod
    def infer_frame() -> None:
        """图像推理"""
        if np.all(_STATE["frame_buffer"] == 0):
            return

        try:
            encode_success, buf = cv2.imencode('.jpg', _STATE["frame_buffer"], [cv2.IMWRITE_JPEG_QUALITY, 80])
            if not encode_success:
                raise cv2.error("图像编码失败", (), ())

            try:
                buf_bytes = buf.tobytes()  # type: ignore
                b64_data = base64.b64encode(buf_bytes).decode('utf-8')
            except binascii.Error as encode_err:
                raise RuntimeError(f"Base64编码失败: {str(encode_err)[:30]}")

            model_name = str(_STATE["selected_model"])
            gpu_layers = CONFIG["gpu"]["layers"]  # type: ignore
            payload = {
                "model": model_name,
                "prompt": "请精准描述画面内容，控制在15字以内，仅返回描述文本",
                "images": [b64_data],
                "stream": False,
                "options": {"temperature": 0.01, "num_predict": 100, "top_p": 0.1, "gpu_layers": gpu_layers}
            }

            ollama_host = CONFIG["ollama"]["host"]  # type: ignore
            inference_timeout = CONFIG["inference"]["timeout"]  # type: ignore
            resp = SystemUtils.http_request(
                "POST",
                f"{ollama_host}/api/generate",
                json_data=payload,
                timeout=inference_timeout,
                retries=2
            )

            timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            if resp:
                result = str(resp.json()["response"]).strip().replace("\n", "").replace(" ", "")[:15]
                print(f"[INFO] [{timestamp}] 识别结果: {result}")
                TTSManager.speak(result)
            else:
                raise RuntimeError("推理请求失败，无响应")

        except cv2.error as cv_err:
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            print(f"[ERROR] [{timestamp}] 图像处理异常: {str(cv_err)[:50]}")
            TTSManager.speak("识别失败")
        except (binascii.Error, RuntimeError, TypeError) as infer_err:
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            print(f"[ERROR] [{timestamp}] 推理异常: {str(infer_err)[:50]}")
            TTSManager.speak("识别失败")


# ====================== TTS管理类 ======================
class TTSManager:
    """TTS语音管理类"""

    @staticmethod
    def init() -> object | None:
        """初始化TTS引擎"""
        tts_enabled = CONFIG["tts_enabled"]  # type: ignore
        if not tts_enabled or not SystemUtils.is_windows():
            print("[INFO] TTS语音播报已禁用")
            return None

        try:
            import win32com.client
            speaker = win32com.client.Dispatch("SAPI.SpVoice")

            for voice in speaker.GetVoices():
                voice_id = str(voice.Id).lower()
                if "zh-cn" in voice_id:
                    speaker.Voice = voice
                    break

            speaker.Volume = 100
            speaker.Rate = 0
            speaker.Speak("", 1)
            print("[INFO] TTS语音引擎初始化成功")
            return speaker
        except (ImportError, AttributeError, RuntimeError) as tts_err:
            print(f"[ERROR] TTS初始化失败: {str(tts_err)[:30]}")
            return None

    @staticmethod
    def speak(text: str) -> None:
        """异步语音播报"""
        tts_enabled = CONFIG["tts_enabled"]  # type: ignore
        if not tts_enabled or not _STATE["tts_speaker"]:
            return

        def _speak_worker():
            try:
                text_str = str(text).strip()
                if text_str:
                    _STATE["tts_speaker"].Speak(text_str, 0)
            except (AttributeError, RuntimeError) as speak_err:
                print(f"[WARNING] TTS播报失败: {str(speak_err)[:30]}")

        threading.Thread(target=_speak_worker, daemon=True).start()


# ====================== 依赖检查类 ======================
class DependencyChecker:
    """依赖检查类"""

    @staticmethod
    def check_all() -> bool:
        """检查所有依赖"""
        required = {
            "cv2": "opencv-python",
            "numpy": "numpy",
            "requests": "requests",
            "websockets": "websockets"
        }
        if SystemUtils.is_windows():
            required["win32com.client"] = "pywin32"

        missing = []
        for imp_name, pkg_name in required.items():
            try:
                __import__(imp_name.split(".")[0])
            except ImportError:
                missing.append(pkg_name)

        if missing:
            print(f"[ERROR] 缺失依赖包: {', '.join(missing)}")
            print("[INFO] 正在自动安装依赖...")
            pip_cmd = [sys.executable, "-m", "pip", "install", "-U", "-i",
                       "https://pypi.tuna.tsinghua.edu.cn/simple"] + missing
            success, _ = SystemUtils.execute_command(pip_cmd, timeout=300.0)
            if not success:
                print(f"[ERROR] 依赖安装失败，请手动执行：pip install {' '.join(missing)}")
                return False

        ollama_exe = OllamaManager.get_ollama_path()
        if not os.path.exists(ollama_exe):
            check_cmd = ["where", "ollama"] if SystemUtils.is_windows() else ["which", "ollama"]
            success, _ = SystemUtils.execute_command(check_cmd, timeout=5.0)
            if not success:
                print("[ERROR] 未检测到Ollama，请先安装（https://ollama.com/download）")
                return False

        return True


# ====================== 主程序类 ======================
class MainApplication:
    """主应用类"""

    @staticmethod
    def run() -> None:
        """运行主程序"""
        if SystemUtils.is_windows() and not SystemUtils.is_admin():
            try:
                SystemUtils.run_as_admin(__file__)
                return
            except Exception as admin_run_err:
                print(f"[WARNING] 未以管理员身份运行: {str(admin_run_err)[:30]}")

        print("=" * 60 + "\n实时视频分析系统 - 树莓派/PC双模式版\n" + "=" * 60)

        if not DependencyChecker.check_all():
            input("\n按回车退出...")
            return

        if not VideoProcessor.select_run_mode() or not OllamaManager.select_model() or not OllamaManager.pull_model() or not OllamaManager.start_service():
            input("\n按回车退出...")
            return

        _STATE["tts_speaker"] = TTSManager.init()
        if _STATE["tts_speaker"]:
            mode_str = str(_STATE["mode"])
            model_str = str(_STATE["selected_model"])
            TTSManager.speak(f"系统已启动，{mode_str}模式，使用{model_str}模型分析")

        if _STATE["mode"] == "camera":
            threading.Thread(target=VideoProcessor.camera_worker, daemon=True).start()
        else:
            VideoProcessor.start_websocket_worker()

        try:
            cv2.namedWindow("Video Analysis", cv2.WINDOW_NORMAL)
            disp_width = CONFIG["display"]["width"]  # type: ignore
            disp_height = CONFIG["display"]["height"]  # type: ignore
            cv2.resizeWindow("Video Analysis", disp_width, disp_height)
        except cv2.error as win_err:
            print(f"[WARNING] 创建显示窗口失败: {str(win_err)[:30]}")

        last_infer = time.time()
        infer_interval = CONFIG["inference"]["interval"]  # type: ignore
        exit_keys = CONFIG["exit_keys"]  # type: ignore

        while _STATE["running"]:
            current_time = time.time()
            if current_time - last_infer >= infer_interval:
                threading.Thread(target=VideoProcessor.infer_frame, daemon=True).start()
                last_infer = current_time

            try:
                if not np.all(_STATE["frame_buffer"] == 0):
                    cv2.imshow("Video Analysis", _STATE["frame_buffer"])
            except cv2.error as show_err:
                print(f"[WARNING] 视频显示异常: {str(show_err)[:20]}")

            key = cv2.waitKey(1) & 0xFF
            if key in exit_keys:
                _STATE["running"] = False
                print("\n[INFO] 检测到退出按键，正在关闭程序...")
                TTSManager.speak("程序即将退出")
                break
            elif key == ord('m'):
                VideoProcessor.select_run_mode()
                if _STATE["mode"] == "camera":
                    threading.Thread(target=VideoProcessor.camera_worker, daemon=True).start()
                else:
                    VideoProcessor.start_websocket_worker()

        print("[INFO] 正在释放资源...")
        cv2.destroyAllWindows()

        if _STATE["ws_loop"]:
            try:
                if _STATE["ws_task"]:
                    _STATE["ws_task"].cancel()
                _STATE["ws_loop"].stop()
                _STATE["ws_loop"].close()
            except Exception as ws_clean_err:
                print(f"[WARNING] WebSocket清理失败: {str(ws_clean_err)[:30]}")

        OllamaManager.stop_service()

        TTSManager.speak("系统已退出")
        print("[INFO] 系统正常退出，感谢使用！")


# ====================== 程序入口 ======================
if __name__ == "__main__":
    try:
        MainApplication.run()
    except KeyboardInterrupt:
        print("\n[INFO] 用户手动中断程序")
    except Exception as main_err:
        print(f"\n[FATAL ERROR] 程序异常退出: {str(main_err)}")
        input("\n按回车退出...")