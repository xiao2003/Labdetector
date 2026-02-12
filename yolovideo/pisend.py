import asyncio
import websockets
import cv2
import numpy as np
from picamera2 import Picamera2
import nest_asyncio
import time
import os

# 启用nest_asyncio，允许Jupyter中嵌套运行异步任务
nest_asyncio.apply()

# 全局变量
server_task = None
picam2 = None
# 核心配置（仅保留通用参数）
TARGET_FPS = 30
MAX_LATENCY = 50
JPEG_QUALITY = 70  # 低质量换快编码，降低延迟
CAMERA_RES = (1920, 1080)

# 关闭libcamera冗余日志，减少干扰
os.environ["LIBCAMERA_LOG_LEVELS"] = "ERROR"


async def init_camera():
    """极简通用摄像头初始化（适配所有Picamera2版本）"""
    global picam2
    if picam2 is not None:
        return

    try:
        picam2 = Picamera2()
        # 1. 仅使用通用配置（移除所有版本不兼容参数）
        # create_video_configuration默认会适配硬件缓存，无需手动设置
        camera_config = picam2.create_video_configuration(
            main={
                "size": CAMERA_RES,
                "format": "RGB888"
            }
        )

        # 2. 仅使用通用API配置（移除set_buffer_count等不兼容方法）
        picam2.configure(camera_config)

        # 3. 启动摄像头（纯通用方法）
        picam2.start()
        await asyncio.sleep(1.2)  # 足够长的等待时间，适配硬件

        # 4. 清空初始帧，避免脏数据
        for _ in range(6):
            picam2.capture_array()

        print(f"✅ 摄像头初始化完成 | ov5647 | {CAMERA_RES}@{TARGET_FPS}FPS")
    except Exception as e:
        print(f"❌ 摄像头初始化失败：{str(e)}")
        picam2 = None  # 初始化失败重置


async def video_stream(websocket):
    """低延迟视频流推送（纯通用API）"""
    global picam2
    print("📡 PC已连接，开始传输视频流...")

    # JPEG编码参数（轻量化）
    encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY]
    # 帧率精准控速（软件层面控速，不依赖硬件参数）
    frame_interval = 1.0 / TARGET_FPS
    last_frame_time = time.time()

    try:
        while True:
            # 摄像头未初始化则重试
            if picam2 is None:
                await init_camera()
                await asyncio.sleep(0.5)
                continue

            # 1. 采集视频帧（纯默认通用方法）
            frame_start = time.time_ns()
            frame = picam2.capture_array()  # 移除所有自定义参数

            # 2. 垂直翻转（解决上下颠倒）
            frame = cv2.flip(frame, 0)

            # 3. 快速编码（减少CPU开销）
            _, img_encoded = cv2.imencode('.jpg', frame, encode_param)
            frame_data = img_encoded.tobytes()

            # 4. 立即发送（无缓存，低延迟）
            await websocket.send(frame_data)

            # 5. 软件控速（保证30FPS，不依赖硬件配置）
            current_time = time.time()
            elapsed = current_time - last_frame_time
            sleep_time = frame_interval - elapsed
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)
            last_frame_time = current_time

            # 6. 延迟统计（每5秒打印）
            if int(current_time) % 5 == 0:
                capture_encode_latency = (time.time_ns() - frame_start) / 1000000
                print(f"📊 采集+编码延迟：{capture_encode_latency:.1f}ms (≤15ms达标)")

    except websockets.exceptions.ConnectionClosed:
        print("🔌 PC断开连接，停止传输")
    except Exception as e:
        print(f"❌ 视频流传输异常：{str(e)}")
        # 异常重置摄像头
        if picam2:
            picam2.stop()
            picam2 = None


async def start_server():
    """启动WebSocket服务器（通用版）"""
    global server_task
    HOST = "192.168.31.31"
    PORT = 8001

    # 先初始化摄像头
    await init_camera()

    # 创建低延迟WebSocket服务器（通用配置）
    server = await websockets.serve(
        video_stream,
        HOST,
        PORT,
        ping_interval=None,
        max_size=None,
        compression=None,
        close_timeout=0.1
    )

    print(f"\n🚀 树莓派视频流服务器启动成功")
    print(f"🌐 地址：ws://{HOST}:{PORT}")
    print(f"⚡ 配置：{CAMERA_RES}@{TARGET_FPS}FPS | 目标延迟≤{MAX_LATENCY}ms")
    print("🔧 停止服务器：执行 await stop_server()")

    server_task = server
    await server.wait_closed()


async def stop_server():
    """停止服务器并释放资源（通用版）"""
    global server_task, picam2
    if server_task:
        server_task.close()
        await server_task.wait_closed()
        print("🛑 服务器已停止")
    if picam2:
        picam2.stop()
        picam2.close()
        picam2 = None
        print("📷 摄像头资源已释放")


# 安全启动服务器
async def safe_start():
    try:
        await start_server()
    except Exception as e:
        print(f"⚠️ 服务器启动异常：{str(e)}")
        await stop_server()


# Jupyter启动入口（通用兼容）
server_future = asyncio.ensure_future(safe_start())