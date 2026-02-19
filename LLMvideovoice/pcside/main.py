#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
main.py - 主程序入口
"""

import cv2
import numpy as np
import threading
import subprocess
import ctypes
import sys
import os
import time
import requests
import websockets
import asyncio
from typing import Optional

from core.config import get_config, set_config
from core.logger import console_info, console_error, console_status, console_prompt
from core.tts import speak_async
from core.voice_interaction import get_voice_interaction, is_voice_interaction_available, VoiceInteractionConfig
from core.ai_backend import list_ollama_models, analyze_image
from communication.pcsend import setup_voice_sender, send_voice_result, cleanup_voice_sender

# 获取分辨率配置
resolution = get_config("camera.resolution", (1280, 720))
# 全局状态
_STATE = {
    "running": True,
    "mode": "",  # camera / websocket
    "frame_buffer": np.zeros((resolution[1], resolution[0], 3), np.uint8),
    "tts_available": False,
    "selected_model": "",
    "ai_backend": "",  # "ollama" or "qwen"
    "ws_connected": False,
    "ws_retry_attempts": 0  # WS重试次数
}


def check_dependencies():
    """检查并自动安装所有依赖包"""
    required_packages = ["cv2", "numpy", "requests", "websockets"]
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
                console_info("已选择：本机摄像头模式")  # 移除前面的换行符
                break
            elif choice_idx == 2:
                _STATE["mode"] = "websocket"
                console_info(
                    f"已选择：树莓派WebSocket模式（地址：ws://{get_config('websocket.host')}:{get_config('websocket.port')}）")
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


async def websocket_client():
    """WebSocket客户端：接收树莓派视频流（含重试逻辑）"""
    uri = f"ws://{get_config('websocket.host')}:{get_config('websocket.port')}"
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
        except Exception as e:
            _STATE["ws_retry_attempts"] += 1
            console_error(f"第{_STATE['ws_retry_attempts']}次连接失败: {str(e)[:50]}")
            # 判断是否达到最大重试次数
            if _STATE["ws_retry_attempts"] >= get_config("ws_retry.max_attempts"):
                console_info(f"已达到最大重试次数({get_config('ws_retry.max_attempts')})，将退出")
                _STATE["mode"] = "camera"
                _STATE["running"] = False
                console_info("切换到本机摄像头模式运行")
                speak_async("树莓派连接失败，切换到本机摄像头模式")
                # 启动本机摄像头线程
                threading.Thread(target=camera_worker, daemon=True).start()
                break
            else:
                # 未达最大次数，自动重试
                retry_interval = get_config("ws_retry.interval")
                console_info(
                    f"{retry_interval}秒后自动重试（剩余{get_config('ws_retry.max_attempts') - _STATE['ws_retry_attempts']}次）")
                time.sleep(retry_interval)


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
    console_prompt("注意：语音交互配置已移至config.ini文件，可直接编辑修改")
    console_prompt("默认配置文件位置：core/config.ini")
    console_prompt("按回车继续...")
    input()

    # 不再需要通过命令行设置参数，直接从配置文件读取
    config = VoiceInteractionConfig()

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
    if not voice_interaction.is_running:
        if voice_interaction.start():
            console_info("语音交互功能已启用")
            return True
        else:
            console_info("语音交互功能启动失败")
            return False
    else:
        console_info("语音交互服务已在运行")
        return True


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
    if _STATE["ai_backend"] == "ollama" or _STATE["ai_backend"] == "qwen":
        try:
            result = analyze_image(
                _STATE["frame_buffer"],
                _STATE["selected_model"]
            )
            # 识别结果属于 VOICE 输出
            if _STATE["mode"] == "websocket":
                # 在websocket模式下，发送到树莓派
                full_text = f"[voice]{result}"
                if send_voice_result(full_text):
                    console_info(f"已发送到树莓派: {full_text}")
                else:
                    console_error(f"发送到树莓派失败: {full_text}")
            else:
                # 在本机摄像头模式下，本地播报
                speak_async(result)
        except Exception as e:
            console_error(f"推理异常: {str(e)[:50]}")
            if _STATE["mode"] == "websocket":
                send_voice_result("[voice]识别失败")
            else:
                speak_async("识别失败")


def main():
    """主程序入口"""
    # 仅在Windows系统下检查管理员权限
    if os.name == 'nt':
        try:
            if not ctypes.windll.shell32.IsUserAnAdmin():
                ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, __file__, None, 1)
                return
        except Exception as e:
            console_error(f"管理员权限检查失败: {str(e)}")

    console_prompt("=" * 60)
    console_prompt("实时视频分析系统 - 树莓派/PC双模式版")
    console_prompt("=" * 60)

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


if __name__ == "__main__":
    main()