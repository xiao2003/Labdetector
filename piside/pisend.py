import asyncio
import websockets
import cv2
import numpy as np
from picamera2 import Picamera2
import nest_asyncio
import time
import os
import statistics
import threading
import subprocess
import shutil
import sys

# 启用nest_asyncio，允许Jupyter中嵌套运行异步任务
nest_asyncio.apply()

# 简洁线程安全的控制台输出管理，避免视频实时状态和信息日志互相打架
print_lock = threading.Lock()
_status_line = ""
# 日志文件（默认放到当前用户家目录，Linux 环境下有效）
# 如果环境变量 LABDETECTOR_LOG 被设置则使用它；否则在默认文件名前加上时间戳前缀，避免日志文件冲突
env_log = os.getenv('LABDETECTOR_LOG')
if env_log:
    LOG_FILE_PATH = env_log
else:
    base_default = os.path.expanduser('~/labdetector.log')
    log_dir = os.path.dirname(base_default) or os.path.expanduser('~')
    base_name = os.path.basename(base_default)
    ts = time.strftime('%Y%m%d_%H%M%S')
    LOG_FILE_PATH = os.path.join(log_dir, f"{ts}_{base_name}")
# 用于序列化文件写入的锁
log_lock = threading.Lock()


def write_log(level: str, text: str):
    """将带时间戳的日志写入到 LOG_FILE_PATH（追加）。

    level 例如 '[INFO]' '[STATUS]' '[ERROR]'
    """
    # File name already includes a timestamp prefix to avoid collisions.
    # Per request, individual log entries should NOT include timestamps — only level and message.
    line = f"{level} {text}\n"
    try:
        # 确保日志目录存在
        log_dir = os.path.dirname(LOG_FILE_PATH)
        if log_dir and not os.path.exists(log_dir):
            try:
                os.makedirs(log_dir, exist_ok=True)
            except Exception:
                pass
        with log_lock:
            with open(LOG_FILE_PATH, 'a', encoding='utf-8') as f:
                f.write(line)
    except Exception:
        # 忽略写日志失败，避免影响主逻辑
        pass


def console_status(text: str):
    """在同一行显示实时状态（不换行），用于视频延迟/质量等实时监控。"""
    global _status_line
    with print_lock:
        _status_line = text
        # 记录到日志（状态）
        write_log('[STATUS]', text)
        try:
            print('\r' + text, end='', flush=True)
        except Exception:
            # 退化为普通输出
            print(text)


def console_info(text: str):
    """打印一条信息行，前缀 [INFO]，并尽量不破坏当前的状态行显示。"""
    global _status_line
    with print_lock:
        # 清除状态行（覆盖为空格），再打印信息行
        if _status_line:
            try:
                print('\r' + ' ' * len(_status_line), end='\r', flush=True)
            except Exception:
                pass
        # 先写日志
        write_log('[INFO]', text)
        print(f"[INFO] {text}")
        # 恢复状态行显示（不换行）
        if _status_line:
            try:
                print('\r' + _status_line, end='', flush=True)
            except Exception:
                pass


def check_and_install_requirements(auto_install: bool = True):
    """检查运行所需的 Python 包和系统工具；尝试在当前 Python 环境中 pip 安装纯 Python 依赖。

    返回 dict，key 为依赖名，value 为 (status, message)。在树莓派（Linux）中，对于非 pip 可安装的包（如 picamera2 或 espeak），
    会打印 apt 安装提示而不是尝试盲目安装。
    """
    requirements = {
        'websockets': 'websockets',
        'nest_asyncio': 'nest_asyncio',
        'opencv': 'opencv-python',
        'pyttsx3': 'pyttsx3',
        'numpy': 'numpy'
    }

    results = {}

    for key, pip_name in requirements.items():
        # map key to import check
        try:
            if key == 'opencv':
                __import__('cv2')
            else:
                __import__(key)
            results[key] = ('ok', 'already installed')
        except Exception:
            msg = ''
            if not auto_install:
                msg = 'missing'
                results[key] = ('missing', msg)
                console_info(f"依赖缺失：{key}（pip 包名：{pip_name}）")
                continue

            # 对于 opencv/numpy/pyttsx3/websockets/nest_asyncio，尝试 pip 安装
            try:
                console_info(f"正在尝试安装 Python 包：{pip_name} ...")
                subprocess.check_call([sys.executable, '-m', 'pip', 'install', '--upgrade', pip_name])
                results[key] = ('installed', f'{pip_name} installed')
                console_info(f"已安装：{pip_name}")
            except Exception as e:
                results[key] = ('failed', str(e))
                console_info(f"自动安装失败：{pip_name}，请手动运行：{sys.executable} -m pip install {pip_name}")

    # 专门检查 picamera2（可能需要 apt，在树莓派上通常不是 pip 安装可行）
    try:
        __import__('picamera2')
        results['picamera2'] = ('ok', 'already installed')
    except Exception:
        results['picamera2'] = ('missing', 'picamera2 not importable')
        console_info("警告：未检测到 picamera2 模块；在 Raspberry Pi 上通常需要使用 apt 安装或官方方法。示例：\n  sudo apt update; sudo apt install -y python3-picamera2 libcamera-apps")

    # 检查 espeak
    try:
        if shutil.which('espeak') is not None:
            results['espeak'] = ('ok', 'espeak available')
        else:
            results['espeak'] = ('missing', 'espeak not found')
            console_info("提示：未检测到系统命令 espeak；若需要TTS可运行：sudo apt install -y espeak")
    except Exception:
        results['espeak'] = ('unknown', '')

    console_info('依赖检查完成')
    # 在 Jupyter 环境中，某些刚安装的包可能需要重启内核才能被导入；提示用户
    console_info('注意：如果安装了新的包，Jupyter 内核可能需要重启以使其生效')
    return results

# 全局变量
server_task = None
picam2 = None
client_websocket = None  # 记录客户端连接
bandwidth_history = []  # 带宽历史记录（ms）
quality_level = 3  # 编码质量等级（1-5，对应JPEG质量30/50/70/85/95）
quality_map = {1: 30, 2: 50, 3: 70, 4: 85, 5: 95}

# TTS 队列：用于串行播放，避免语音叠加
tts_queue = None
tts_task = None

# 核心配置
TARGET_FPS = 30
MAX_LATENCY = 50
BASE_CAMERA_RES = (1920, 1080)  # 原始分辨率
DOWNSCALE_RATIO = 1  # 降采样比例（可根据需求调整）
ROI_REGION = (0.2, 0.2, 0.8, 0.8)  # ROI区域（x1,y1,x2,y2 相对坐标）
BANDWIDTH_CHECK_INTERVAL = 3  # 带宽检测间隔（秒）
QUALITY_ADJUST_THRESHOLD = 10  # 质量调整阈值（延迟波动超过该值触发）

# 关闭libcamera冗余日志
os.environ["LIBCAMERA_LOG_LEVELS"] = "ERROR"


# ====================== TTS (text-to-speech) 支持 ======================
# 尝试使用 pyttsx3（跨平台），如果不可用则回退到系统命令（espeak）
_TTS_ENGINE = None


def init_tts():
    """初始化TTS：优先使用pyttsx3，失败时使用系统命令（Linux上的espeak）。"""
    global _TTS_ENGINE
    # 在树莓派/大多数 Linux 设备上优先使用 espeak（轻量且常见），否则尝试 pyttsx3
    try:
        if sys.platform.startswith("linux"):
            if shutil.which("espeak") is not None:
                _TTS_ENGINE = "espeak"
                console_info("TTS: 使用 espeak（Linux 优先）")
                return True
            # 回退到 pyttsx3
            try:
                import pyttsx3
                engine = pyttsx3.init()
                engine.setProperty('rate', 150)
                engine.setProperty('volume', 1.0)
                _TTS_ENGINE = engine
                console_info("TTS: 使用 pyttsx3（回退）")
                return True
            except Exception:
                pass

        else:
            # 非Linux平台优先使用 pyttsx3（例如Windows）
            try:
                import pyttsx3
                engine = pyttsx3.init()
                engine.setProperty('rate', 150)
                engine.setProperty('volume', 1.0)
                _TTS_ENGINE = engine
                console_info("TTS: 使用 pyttsx3")
                return True
            except Exception:
                pass

        # 最后一次尝试检测 espeak（通用回退）
        if shutil.which("espeak") is not None:
            _TTS_ENGINE = "espeak"
            console_info("TTS: 使用 espeak 回退")
            return True
    except Exception:
        pass

    console_info("未检测到 pyttsx3 或 espeak，文字播报功能将不可用")
    _TTS_ENGINE = None
    return False


def speak_async(text: str):
    """异步播报文本（非阻塞）。"""

    def _speak(t):
        global _TTS_ENGINE
        if not t:
            return
        try:
            if _TTS_ENGINE == "espeak":
                # 使用系统命令播报（Linux）
                subprocess.Popen(["espeak", t])
            elif _TTS_ENGINE is not None:
                # pyttsx3 engine
                try:
                    _TTS_ENGINE.say(t)
                    _TTS_ENGINE.runAndWait()
                except Exception:
                    pass
            else:
                # 无可用TTS
                pass
        except Exception:
            pass

    threading.Thread(target=_speak, args=(text,), daemon=True).start()


def speak_enqueue(text: str):
    """将文本加入 TTS 队列（非阻塞）。如果队列未初始化，会直接调用 speak_async 作为回退。"""
    global tts_queue
    if tts_queue is None:
        # 回退：直接播放
        speak_async(text)
        return

    try:
        # 不等待，尽量快速入队
        tts_queue.put_nowait(text)
    except Exception:
        # 队列满或异常，回退播放
        speak_async(text)


async def tts_worker():
    """串行的 TTS 消费者，确保语音按顺序播放且不重叠。"""
    global tts_queue, _TTS_ENGINE
    while True:
        try:
            text = await tts_queue.get()
            if text is None:
                break
            # 使用同步 TTS 调用放到线程中运行，避免阻塞事件循环
            await asyncio.to_thread(lambda t=text: speak_async(t))
        except asyncio.CancelledError:
            break
        except Exception:
            continue


# 异步接收来自PC端的文字消息并播报
async def receive_texts(websocket):
    try:
        while True:
            msg = await websocket.recv()
            # websockets库：文本消息为str，二进制为bytes
            if isinstance(msg, str):
                text = msg.strip()
                if text:
                    # 使用 console_info 输出，前缀 [INFO]，避免与单行状态输出冲突
                    console_info(f"📨 接收到文字: {text}")
                    # 将文本加入 TTS 队列，保证串行播放，避免叠加
                    try:
                        speak_enqueue(text)
                    except Exception:
                        speak_async(text)
            else:
                # 忽略二进制（视频/其他）
                continue
    except websockets.exceptions.ConnectionClosed:
        # 连接关闭，退出任务
        return
    except Exception as e:
        console_info(f"❌ 接收文字消息异常：{str(e)}")
        return


async def init_camera():
    """初始化摄像头（兼容所有Picamera2版本）"""
    global picam2
    if picam2 is not None:
        return

    try:
        picam2 = Picamera2()
        camera_config = picam2.create_video_configuration(
            main={
                "size": BASE_CAMERA_RES,
                "format": "RGB888"
            }
        )
        picam2.configure(camera_config)
        picam2.start()
        await asyncio.sleep(1.2)

        # 清空初始帧
        for _ in range(6):
            picam2.capture_array()

        console_info(f"✅ 摄像头初始化完成 | {BASE_CAMERA_RES}@{TARGET_FPS}FPS")
        console_info(f"📐 降采样比例：{DOWNSCALE_RATIO} | ROI区域：{ROI_REGION}")
    except Exception as e:
        console_info(f"❌ 摄像头初始化失败：{str(e)}")
        picam2 = None


def process_frame(frame):
    """帧预处理：降采样 + ROI裁剪"""
    # 1. 降采样
    h, w = frame.shape[:2]
    new_w = int(w * DOWNSCALE_RATIO)
    new_h = int(h * DOWNSCALE_RATIO)
    frame_downscaled = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_LINEAR)

    # 2. ROI区域裁剪
    roi_x1 = int(new_w * ROI_REGION[0])
    roi_y1 = int(new_h * ROI_REGION[1])
    roi_x2 = int(new_w * ROI_REGION[2])
    roi_y2 = int(new_h * ROI_REGION[3])
    frame_roi = frame_downscaled[roi_y1:roi_y2, roi_x1:roi_x2]

    # 3. 垂直翻转（解决画面颠倒）
    frame_roi = cv2.flip(frame_roi, 0)

    return frame_roi


async def adjust_quality():
    """动态调整编码质量（基于带宽延迟）"""
    global quality_level, bandwidth_history
    if len(bandwidth_history) < 5:
        return

    # 计算延迟均值和标准差
    latency_mean = statistics.mean(bandwidth_history)
    latency_std = statistics.stdev(bandwidth_history) if len(bandwidth_history) > 1 else 0

    # 延迟过高→降低质量
    if latency_mean > MAX_LATENCY + 10 and quality_level > 1:
        quality_level -= 1
        console_info(f"📉 带宽不足（延迟{latency_mean:.1f}ms），编码质量降至等级{quality_level}（{quality_map[quality_level]}）")
    # 延迟过低→提升质量
    elif latency_mean < MAX_LATENCY - 10 and quality_level < 5 and latency_std < QUALITY_ADJUST_THRESHOLD:
        quality_level += 1
        console_info(f"📈 带宽充足（延迟{latency_mean:.1f}ms），编码质量升至等级{quality_level}（{quality_map[quality_level]}）")

    # 清空历史记录
    bandwidth_history = []


async def video_stream(websocket):
    """低延迟视频流推送（带动态质量调整）"""
    global picam2, client_websocket
    client_websocket = websocket
    console_info("📡 PC已连接，开始传输视频流...")

    encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), quality_map[quality_level]]
    frame_interval = 1.0 / TARGET_FPS
    last_frame_time = time.time()
    last_bandwidth_check = time.time()

    # 启动接收文字消息的并发任务（负责接收PC回传的文字并播报）
    recv_task = asyncio.create_task(receive_texts(websocket))

    try:
        while True:
            if picam2 is None:
                await init_camera()
                await asyncio.sleep(0.5)
                continue

            # 1. 采集并预处理帧
            frame_start = time.time_ns()
            frame = picam2.capture_array()
            frame_processed = process_frame(frame)

            # 2. 动态调整编码质量
            current_time = time.time()
            if current_time - last_bandwidth_check >= BANDWIDTH_CHECK_INTERVAL:
                await adjust_quality()
                encode_param[1] = quality_map[quality_level]
                last_bandwidth_check = current_time

            # 3. 编码并发送
            _, img_encoded = cv2.imencode('.jpg', frame_processed, encode_param)
            frame_data = img_encoded.tobytes()
            await websocket.send(frame_data)

            # 4. 统计延迟并记录带宽
            capture_encode_latency = (time.time_ns() - frame_start) / 1000000
            bandwidth_history.append(capture_encode_latency)

            # 5. 帧率控制
            elapsed = current_time - last_frame_time
            sleep_time = frame_interval - elapsed
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)
            last_frame_time = current_time

            # 6. 打印监控信息
            if int(current_time) % 5 == 0:
                console_status(
                    f"📊 延迟：{capture_encode_latency:.1f}ms | 质量等级：{quality_level} | 分辨率：{frame_processed.shape[1]}x{frame_processed.shape[0]}")

    except websockets.exceptions.ConnectionClosed:
        console_info("🔌 PC断开连接，停止传输")
    except Exception as e:
        console_info(f"❌ 视频流传输异常：{str(e)}")
        if picam2:
            picam2.stop()
            picam2 = None
    finally:
        # 确保接收任务被取消/清理
        try:
            if not recv_task.done():
                recv_task.cancel()
        except Exception:
            pass
        client_websocket = None


async def start_server():
    """启动WebSocket服务器"""
    global server_task
    HOST = "192.168.31.31"
    PORT = 8001

    await init_camera()

    server = await websockets.serve(
        video_stream,
        HOST,
        PORT,
        ping_interval=None,
        max_size=None,
        compression=None,
        close_timeout=0.1
    )

    console_info(f"🚀 树莓派视频流服务器启动成功")
    console_info(f"🌐 地址：ws://{HOST}:{PORT}")
    console_info(f"⚡ 初始配置：{BASE_CAMERA_RES}→{int(BASE_CAMERA_RES[0] * DOWNSCALE_RATIO)}x{int(BASE_CAMERA_RES[1] * DOWNSCALE_RATIO)} | 目标延迟≤{MAX_LATENCY}ms")
    console_info("🔧 停止服务器：执行 await stop_server()")

    server_task = server
    await server.wait_closed()


async def stop_server():
    """停止服务器并释放资源"""
    global server_task, picam2, client_websocket, tts_task, tts_queue
    if server_task:
        server_task.close()
        await server_task.wait_closed()
        console_info("🛑 服务器已停止")
    if picam2:
        picam2.stop()
        picam2.close()
        picam2 = None
        console_info("📷 摄像头资源已释放")

    # 清理 TTS 相关任务
    try:
        if tts_queue is not None:
            # 发送 None 作为终止信号
            try:
                await tts_queue.put(None)
            except Exception:
                pass
        if tts_task is not None:
            tts_task.cancel()
            try:
                await tts_task
            except Exception:
                pass
    except Exception:
        pass

    client_websocket = None


async def safe_start():
    """安全启动服务器"""
    global tts_queue, tts_task
    try:
        # 初始化TTS（如果可用），以便接收的文字可以播报
        try:
            if init_tts():
                # 创建 TTS 队列和任务，队列长度限制以防内存膨胀
                tts_queue = asyncio.Queue(maxsize=16)
                tts_task = asyncio.create_task(tts_worker())
        except Exception:
            pass

        # 输出日志文件路径，方便在树莓派/Jupyter 中查找
        try:
            console_info(f"日志文件路径：{LOG_FILE_PATH}")
        except Exception:
            pass

        # 检查并安装依赖（非阻塞）
        try:
            await asyncio.to_thread(check_and_install_requirements, True)
        except Exception as e:
            console_info(f"依赖检查/安装异常：{str(e)}")

        await start_server()
    except Exception as e:
        console_info(f"⚠️ 服务器启动异常：{str(e)}")
        await stop_server()


# Jupyter启动入口
server_future = asyncio.ensure_future(safe_start())