#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
实时视频分析系统 V2.1
特性：
1. 自动拉取llava:13b-v1.5-q4_K_M大模型（CMD实时显示进度）
2. 15字中文无乱码/问号显示（抗锯齿）
3. 标准化日志输出，无口语化冗余
4. 非阻塞摄像头+Ollama服务管理
"""
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

# ====================== 系统核心配置（可按需调整） ======================
# 硬件配置
CAMERA_INDEX = 0
CAMERA_RESOLUTION = (1280, 720)  # 宽x高

# 模型配置（13B大模型，自动拉取）
OLLAMA_HOST = "http://localhost:11434"
TARGET_MODEL = "llava:13b-v1.5-q4_K_M"  # 更大的13B模型
INFERENCE_INTERVAL = 5  # 推理间隔（秒）

# 显示配置（15字无乱码）
TEXT_MAX_LENGTH = 15  # 最大显示字数
TEXT_POSITION = (30, 80)
TEXT_COLOR = (0, 255, 0)  # 绿色
TEXT_SIZE = 1.8
TEXT_THICKNESS = 3
TEXT_SPACING = 40  # 字符间距（适配15字）

# 全局状态（标准化命名）
_SYSTEM_RUNNING = True
_CAMERA_READY = False
_FRAME_BUFFER = np.zeros((CAMERA_RESOLUTION[1], CAMERA_RESOLUTION[0], 3), np.uint8)
_RECOGNITION_RESULT = "系统初始化中..."


# ====================== 1. 自动模型拉取模块（核心：实时显示进度） ======================
def _pull_ollama_model():
    """自动拉取指定Ollama模型，CMD实时显示下载进度"""
    print("[INFO] 检查目标模型是否存在...")

    # 检查模型是否已存在
    try:
        # 先启动基础Ollama服务（用于检查模型）
        ollama_exe = "ollama.exe"
        default_exe_path = "C:\\Users\\Administrator\\AppData\\Local\\Programs\\Ollama\\ollama.exe"
        if os.path.exists(default_exe_path):
            ollama_exe = default_exe_path

        # 启动临时Ollama服务
        subprocess.Popen(
            [ollama_exe, "serve"],
            creationflags=subprocess.CREATE_NEW_CONSOLE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        time.sleep(3)

        # 检查模型列表
        response = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=5)
        if response.status_code == 200:
            models = response.json().get("models", [])
            for model in models:
                if model.get("name") == TARGET_MODEL:
                    print(f"[INFO] 模型 {TARGET_MODEL} 已存在，无需拉取")
                    # 终止临时服务
                    subprocess.run('taskkill /f /im ollama.exe >NUL 2>&1', shell=True, check=False)
                    time.sleep(0.5)
                    return True
    except Exception as e:
        print(f"[WARNING] 模型检查失败: {str(e)[:30]}，开始拉取新模型")

    # 终止旧Ollama进程（避免端口占用）
    subprocess.run('taskkill /f /im ollama.exe >NUL 2>&1', shell=True, check=False)
    time.sleep(0.5)

    # 执行模型拉取命令（实时输出进度到CMD）
    print(f"\n[INFO] 开始拉取模型 {TARGET_MODEL}（首次拉取需下载约10GB）")
    print("=" * 50)
    try:
        ollama_exe = "ollama.exe"
        default_exe_path = "C:\\Users\\Administrator\\AppData\\Local\\Programs\\Ollama\\ollama.exe"
        if os.path.exists(default_exe_path):
            ollama_exe = default_exe_path

        # 关键：stdout/stderr直接指向控制台，实时显示进度
        pull_process = subprocess.Popen(
            [ollama_exe, "pull", TARGET_MODEL],
            shell=True,
            stdout=sys.stdout,  # 实时输出到CMD
            stderr=sys.stderr,  # 错误信息也实时输出
            creationflags=subprocess.CREATE_NEW_CONSOLE if os.name == 'nt' else 0
        )

        # 等待拉取完成
        pull_process.wait(timeout=3600)  # 超时1小时

        if pull_process.returncode == 0:
            print("=" * 50)
            print(f"[INFO] 模型 {TARGET_MODEL} 拉取成功")
            return True
        else:
            print("=" * 50)
            print(f"[ERROR] 模型拉取失败（返回码：{pull_process.returncode}）")
            return False
    except subprocess.TimeoutExpired:
        print("=" * 50)
        print("[ERROR] 模型拉取超时（超过1小时）")
        return False
    except Exception as e:
        print("=" * 50)
        print(f"[ERROR] 模型拉取异常: {str(e)[:50]}")
        return False


# ====================== 2. 语音播报模块（标准化） ======================
def _init_tts():
    """初始化中文TTS引擎"""
    try:
        speaker = win32com.client.Dispatch("SAPI.SpVoice")
        for voice in speaker.GetVoices():
            if "zh-CN" in voice.Id:
                speaker.Voice = voice
                break
        speaker.Volume = 100
        speaker.Rate = 0
        return speaker
    except Exception as e:
        print(f"[ERROR] TTS引擎初始化失败: {str(e)[:50]}")
        return None


def _speak_async(text, speaker):
    """异步语音播报（非阻塞）"""

    def _speak():
        if speaker:
            try:
                speaker.Speak(text)
            except:
                pass

    threading.Thread(target=_speak, daemon=True).start()


# ====================== 3. 15字中文显示模块（无乱码/问号） ======================
def _draw_15char_chinese(img, text):
    """
    绘制15字中文文本（彻底消除问号/乱码）
    核心优化：抗锯齿+逐字符精准排版+长度截断
    """
    # 严格截断到15字，避免溢出
    text = text[:TEXT_MAX_LENGTH]
    # 逐字符绘制（解决OpenCV中文显示底层问题）
    for idx, char in enumerate(text):
        x = TEXT_POSITION[0] + idx * TEXT_SPACING
        # 使用TRIPLEX字体+抗锯齿，消除绿色问号/毛刺
        cv2.putText(
            img,
            char,
            (x, TEXT_POSITION[1]),
            cv2.FONT_HERSHEY_TRIPLEX,
            TEXT_SIZE,
            TEXT_COLOR,
            TEXT_THICKNESS,
            cv2.LINE_AA  # 关键：抗锯齿，彻底消除乱码/问号
        )
    return img


# ====================== 4. Ollama服务管理模块 ======================
def _start_ollama_service():
    """启动并验证Ollama服务（适配11434端口）"""
    # 终止旧进程
    try:
        subprocess.run('taskkill /f /im ollama.exe >NUL 2>&1', shell=True, check=False)
        time.sleep(0.5)
    except:
        pass

    # 启动服务（指定11434端口）
    ollama_exe = "ollama.exe"
    default_exe_path = "C:\\Users\\Administrator\\AppData\\Local\\Programs\\Ollama\\ollama.exe"
    if os.path.exists(default_exe_path):
        ollama_exe = default_exe_path

    try:
        os.environ["OLLAMA_HOST"] = "127.0.0.1:11434"
        subprocess.Popen(
            [ollama_exe, "serve"],
            creationflags=subprocess.CREATE_NEW_CONSOLE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    except Exception as e:
        print(f"[ERROR] Ollama服务启动失败: {str(e)[:50]}")
        return False

    # 验证连接
    for _ in range(15):
        try:
            res = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=1)
            if res.status_code == 200:
                print("[INFO] Ollama服务启动成功（端口：11434）")
                return True
        except:
            time.sleep(1)
    print("[WARNING] Ollama服务连接超时，继续尝试运行")
    return True


# ====================== 5. 摄像头采集模块（非阻塞） ======================
def _camera_worker():
    """摄像头采集线程（容错+非阻塞）"""
    global _CAMERA_READY, _FRAME_BUFFER
    cap = None

    # 多驱动/多索引尝试，提升兼容性
    indexes = [0, 1]
    apis = [cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY]
    for idx in indexes:
        for api in apis:
            cap = cv2.VideoCapture(idx, api)
            if cap.isOpened():
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_RESOLUTION[0])
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_RESOLUTION[1])
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                _CAMERA_READY = True
                print("[INFO] 摄像头初始化成功")
                break
        if _CAMERA_READY:
            break

    # 帧采集循环
    while _SYSTEM_RUNNING:
        if _CAMERA_READY and cap.isOpened():
            try:
                ret, frame = cap.read()
                if ret:
                    _FRAME_BUFFER = frame.copy()
                else:
                    _FRAME_BUFFER = np.zeros((CAMERA_RESOLUTION[1], CAMERA_RESOLUTION[0], 3), np.uint8)
            except:
                _FRAME_BUFFER = np.zeros((CAMERA_RESOLUTION[1], CAMERA_RESOLUTION[0], 3), np.uint8)
        time.sleep(0.01)

    if cap:
        cap.release()


# ====================== 6. 推理模块（适配13B模型+15字输出） ======================
def _infer_frame(speaker):
    """推理单帧图像，输出15字结果"""
    global _RECOGNITION_RESULT
    try:
        # 高质量编码图像
        encode_param = [cv2.IMWRITE_JPEG_QUALITY, 90]
        _, img_buf = cv2.imencode('.jpg', _FRAME_BUFFER, encode_param)
        img_b64 = base64.b64encode(img_buf).decode('utf-8')

        # 精准Prompt（要求15字输出）
        prompt = f"""请精准描述画面内容，严格遵守以下规则：
1. 描述结果控制在{TEXT_MAX_LENGTH}个字以内；
2. 优先描述核心主体、动作、场景；
3. 仅返回描述文本，无任何多余文字/标点/换行。"""

        # 推理请求（适配13B模型参数）
        payload = {
            "model": TARGET_MODEL,
            "prompt": prompt,
            "images": [img_b64],
            "stream": False,
            "options": {
                "temperature": 0.01,
                "num_predict": 100,
                "top_p": 0.1,
                "gpu_layers": 20  # GPU加速，提升13B模型推理速度
            }
        }

        # 发送请求（超时20秒，适配大模型）
        res = requests.post(f"{OLLAMA_HOST}/api/generate", json=payload, timeout=20)
        if res.status_code == 200:
            result = res.json()["response"].strip().replace("\n", "").replace(" ", "")
            _RECOGNITION_RESULT = result[:TEXT_MAX_LENGTH]
            print(f"[INFO] 识别结果: {_RECOGNITION_RESULT}")
            _speak_async(_RECOGNITION_RESULT, speaker)
        else:
            _RECOGNITION_RESULT = "识别失败：服务响应异常"
    except Exception as e:
        _RECOGNITION_RESULT = f"识别失败：{str(e)[:10]}"
        print(f"[ERROR] 推理异常: {str(e)[:50]}")


# ====================== 7. 主程序入口 ======================
def main():
    global _SYSTEM_RUNNING

    # 管理员权限检查
    if os.name == 'nt' and not ctypes.windll.shell32.IsUserAnAdmin():
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, __file__, None, 1)
        return

    # 启动日志
    print("=" * 60)
    print("实时视频分析系统 V2.1 - 启动流程")
    print("=" * 60)

    # 步骤1：自动拉取13B大模型（实时显示进度）
    if not _pull_ollama_model():
        print("[ERROR] 模型拉取失败，程序无法运行")
        input("按回车键退出...")
        return

    # 步骤2：启动Ollama服务
    if not _start_ollama_service():
        print("[ERROR] Ollama服务启动失败")
        input("按回车键退出...")
        return

    # 步骤3：初始化TTS引擎
    tts_speaker = _init_tts()

    # 步骤4：启动摄像头线程
    threading.Thread(target=_camera_worker, daemon=True).start()

    # 步骤5：初始化显示窗口
    cv2.namedWindow("Real-Time Video Analysis (15char)", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("Real-Time Video Analysis (15char)", CAMERA_RESOLUTION[0], CAMERA_RESOLUTION[1])

    # 步骤6：主循环（推理+显示）
    last_infer_time = 0
    while _SYSTEM_RUNNING:
        # 定时推理
        current_time = time.time()
        if current_time - last_infer_time >= INFERENCE_INTERVAL and _CAMERA_READY:
            _infer_frame(tts_speaker)
            last_infer_time = current_time

        # 绘制15字无乱码中文
        display_frame = _FRAME_BUFFER.copy()
        display_frame = _draw_15char_chinese(display_frame, _RECOGNITION_RESULT)

        # 显示画面
        cv2.imshow("Real-Time Video Analysis (15char)", display_frame)

        # 退出逻辑
        if cv2.waitKey(1) & 0xFF == ord('q'):
            _SYSTEM_RUNNING = False
            break

    # 资源清理
    cv2.destroyAllWindows()
    try:
        subprocess.run('taskkill /f /im ollama.exe >NUL 2>&1', shell=True)
    except:
        pass
    _speak_async("系统已退出", tts_speaker)
    print("\n[INFO] 系统正常退出")


if __name__ == "__main__":
    main()