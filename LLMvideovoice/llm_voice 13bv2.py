#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import sys
import time
import threading
import subprocess
import ctypes
import base64
import requests
import cv2
import numpy as np
import win32com.client

# 系统配置（预设常用模型列表，便于用户选择）
CONFIG = {
    "camera": {"index": 0, "resolution": (1280, 720)},
    "ollama": {"host": "http://localhost:11434", "default_models": [
        "llava:7b-v1.5-q4_K_M",  # 轻量模型（约4.5GB）
        "llava:13b-v1.5-q4_K_M",  # 大模型（约10GB，适配5070ti）
        "llava:34b-v1.5-q4_K_M",  # 超大模型（约20GB）
        "llava:latest"  # 最新版模型
    ]},
    "inference": {"interval": 5, "timeout": 20},
    "gpu": {"layers": 35}
}

# 全局状态
_STATE = {
    "running": True,
    "camera_ready": False,
    "frame_buffer": np.zeros((CONFIG["camera"]["resolution"][1], CONFIG["camera"]["resolution"][0], 3), np.uint8),
    "tts_speaker": None,
    "selected_model": ""  # 用户选择的模型
}


def check_dependencies():
    """检查并自动安装所有依赖包"""
    required_packages = ["cv2", "numpy", "requests", "win32com.client"]
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

    # 检查Ollama是否安装
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
        # 启动临时Ollama服务
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

        # 获取模型列表
        resp = requests.get(f"{CONFIG['ollama']['host']}/api/tags", timeout=5)
        if resp.status_code == 200:
            local_models = [m.get("name") for m in resp.json().get("models", []) if "llava" in m.get("name", "")]
            # 终止临时服务
            subprocess.run('taskkill /f /im ollama.exe >NUL 2>&1', shell=True)
            time.sleep(0.5)
            return local_models
    except:
        pass
    return []


def select_model():
    """命令行交互选择模型"""
    print("\n===== 模型选择 =====")
    # 获取本地已安装的模型
    local_models = list_ollama_models()
    # 合并预设模型+本地模型（去重）
    all_models = list(set(CONFIG["ollama"]["default_models"] + local_models))
    all_models.sort()

    # 显示可选模型
    print("可用模型列表（输入序号选择）：")
    for idx, model in enumerate(all_models, 1):
        status = "[已安装]" if model in local_models else "[未安装，将自动拉取]"
        print(f"{idx}. {model} {status}")

    # 支持自定义模型输入
    print(f"{len(all_models) + 1}. 自定义模型")

    # 交互选择
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

    # 检查模型是否已存在
    local_models = list_ollama_models()
    if model in local_models:
        print(f"[INFO] 模型 {model} 已存在，无需拉取")
        return True

    # 终止旧Ollama进程
    subprocess.run('taskkill /f /im ollama.exe >NUL 2>&1', shell=True)
    time.sleep(0.5)

    # 拉取模型（实时显示进度）
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

    # 验证服务连接
    for _ in range(15):
        try:
            if requests.get(f"{CONFIG['ollama']['host']}/api/tags", timeout=1).status_code == 200:
                print("[INFO] Ollama服务就绪")
                return True
        except:
            time.sleep(1)
    print("[WARNING] Ollama连接超时，继续运行")
    return True


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


def camera_worker():
    """摄像头采集线程"""
    cap = None
    indexes = [0, 1]
    apis = [cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY]

    # 尝试初始化摄像头
    for idx in indexes:
        for api in apis:
            cap = cv2.VideoCapture(idx, api)
            if cap.isOpened():
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, CONFIG["camera"]["resolution"][0])
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CONFIG["camera"]["resolution"][1])
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                _STATE["camera_ready"] = True
                print("[INFO] 摄像头初始化成功")
                break
        if _STATE["camera_ready"]:
            break

    # 帧采集循环
    while _STATE["running"]:
        if _STATE["camera_ready"] and cap.isOpened():
            try:
                ret, frame = cap.read()
                if ret:
                    _STATE["frame_buffer"] = frame.copy()
            except:
                pass
        time.sleep(0.01)

    if cap:
        cap.release()


def infer_frame():
    """图像推理（使用选中的模型）"""
    try:
        # 图像编码
        _, buf = cv2.imencode('.jpg', _STATE["frame_buffer"], [cv2.IMWRITE_JPEG_QUALITY, 90])
        b64 = base64.b64encode(buf).decode()

        # 推理请求
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

        # 发送推理请求
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


def main():
    """主程序入口"""
    # 管理员权限检查
    if os.name == 'nt' and not ctypes.windll.shell32.IsUserAnAdmin():
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, __file__, None, 1)
        return

    # 启动日志
    print("=" * 60)
    print("实时视频分析系统")
    print("=" * 60)

    # 步骤1：检查依赖
    if not check_dependencies():
        input("\n按回车退出...")
        return

    # 步骤2：选择模型
    if not select_model():
        input("\n按回车退出...")
        return

    # 步骤3：拉取模型（如需）
    if not pull_ollama_model():
        input("\n按回车退出...")
        return

    # 步骤4：启动Ollama服务
    if not start_ollama_service():
        input("\n按回车退出...")
        return

    # 步骤5：初始化TTS
    _STATE["tts_speaker"] = init_tts()
    if _STATE["tts_speaker"]:
        speak_async(f"系统已启动，使用{_STATE['selected_model']}模型分析")

    # 步骤6：启动摄像头线程
    threading.Thread(target=camera_worker, daemon=True).start()

    # 步骤7：初始化显示窗口
    cv2.namedWindow("Video Analysis", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("Video Analysis", CONFIG["camera"]["resolution"][0], CONFIG["camera"]["resolution"][1])

    # 步骤8：主循环
    last_infer = 0
    while _STATE["running"]:
        current = time.time()
        # 定时推理
        if current - last_infer >= CONFIG["inference"]["interval"] and _STATE["camera_ready"]:
            infer_frame()
            last_infer = current

        # 显示画面
        cv2.imshow("Video Analysis", _STATE["frame_buffer"])
        # 退出逻辑
        if cv2.waitKey(1) & 0xFF == ord('q'):
            _STATE["running"] = False
            break

    # 资源清理
    cv2.destroyAllWindows()
    try:
        subprocess.run('taskkill /f /im ollama.exe >NUL 2>&1', shell=True)
    except:
        pass

    if _STATE["tts_speaker"]:
        speak_async("系统已退出")
    print("\n[INFO] 系统正常退出")


if __name__ == "__main__":
    main()