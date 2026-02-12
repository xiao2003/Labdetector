import asyncio
import websockets
import cv2
import numpy as np
import torch
from ultralytics import YOLO
import time
from scipy.spatial import distance

# -------------------------- 系统级低延迟配置 --------------------------
torch.backends.cudnn.benchmark = True
torch.backends.cudnn.deterministic = False
torch.backends.cuda.matmul.allow_tf32 = True
torch.cuda.empty_cache()
torch.cuda.set_device(0)
torch.cuda.stream(torch.cuda.Stream())

cv2.setNumThreads(1)
cv2.ocl.setUseOpenCL(True)

# -------------------------- 核心配置 --------------------------
WS_SERVER_URL = "ws://192.168.31.31:8001"
YOLO_MODEL_PATH = "yolov8n-pose.pt"
CONF_THRESHOLD = 0.3
INPUT_SIZE = 1280  # 默认1280，平衡延迟和精度
DEVICE = "cuda:0"
TARGET_FPS = 30
MAX_LATENCY = 50
LATENCY_HYSTERESIS = 5  # 延迟滞后阈值，避免频繁切换分辨率

# 手部关键点配置
HAND_KEYPOINTS = {
    "wrist": 0, "thumb1": 1, "thumb2": 2, "thumb3": 3, "thumb4": 4,
    "index1": 5, "index2": 6, "index3": 7, "index4": 8,
    "middle1": 9, "middle2": 10, "middle3": 11, "middle4": 12,
    "ring1": 13, "ring2": 14, "ring3": 15, "ring4": 16,
    "pinky1": 17, "pinky2": 18, "pinky3": 19, "pinky4": 20
}
KEYPOINT_COLORS = {
    "thumb": (0, 0, 255),  # 拇指-红色
    "index": (0, 255, 0),  # 食指-绿色
    "middle": (0, 255, 255),  # 中指-黄色
    "ring": (255, 0, 255),  # 无名指-品红
    "pinky": (255, 0, 0)  # 小指-蓝色
}
ACTION_THRESHOLDS = {
    "fist": 0.15,
    "open_hand": 0.3,
    "thumb_up": 0.4,
    "index_extended": 0.35
}

# 全局变量
latency_list = []
last_recv_time = 0
last_resolution_switch = 0  # 记录上次分辨率切换时间，避免频繁切换

# -------------------------- 环境信息打印 --------------------------
print("=" * 70)
print(f"虚拟环境: D:\PI\.venv")
print(f"PyTorch版本: {torch.__version__} | CUDA版本: {torch.version.cuda}")
print(f"使用GPU: {torch.cuda.get_device_name(0)} (RTX 5070 Ti)")
print(f"配置: 手部细节动作识别 | {INPUT_SIZE}×720@{TARGET_FPS}FPS | 目标延迟≤{MAX_LATENCY}ms")
print("=" * 70)

# -------------------------- 初始化YOLO模型 --------------------------
model = YOLO(YOLO_MODEL_PATH)
model.to(DEVICE)
infer_kwargs = {
    "conf": CONF_THRESHOLD,
    "imgsz": INPUT_SIZE,
    "device": DEVICE,
    "half": True,
    "verbose": False,  # 关闭YOLO自带的日志/窗口输出
    "agnostic_nms": True,
    "max_det": 2,
    "vid_stride": 1,
    "stream": False,
    "classes": [0],
}


# -------------------------- 手部细节识别核心函数 --------------------------
def extract_hand_keypoints(results):
    """提取手部关键点，增加边界检查"""
    hand_keypoints_list = []
    if results[0].keypoints is None:
        return hand_keypoints_list

    pose_keypoints = results[0].keypoints.data.cpu().numpy()
    for person in pose_keypoints:
        # 只提取有足够关键点的手部区域
        if len(person) >= 10 and person[9][2] > CONF_THRESHOLD:  # 左手腕
            hand_kpts = person[9:].reshape(-1, 3)
            # 确保关键点数量足够，不足则补0
            if len(hand_kpts) < len(HAND_KEYPOINTS):
                pad_length = len(HAND_KEYPOINTS) - len(hand_kpts)
                hand_kpts = np.pad(hand_kpts, ((0, pad_length), (0, 0)), mode='constant')
            hand_keypoints_list.append(("left", hand_kpts))

        if len(person) >= 15 and person[15][2] > CONF_THRESHOLD:  # 右手腕
            hand_kpts = person[15:].reshape(-1, 3)
            if len(hand_kpts) < len(HAND_KEYPOINTS):
                pad_length = len(HAND_KEYPOINTS) - len(hand_kpts)
                hand_kpts = np.pad(hand_kpts, ((0, pad_length), (0, 0)), mode='constant')
            hand_keypoints_list.append(("right", hand_kpts))
    return hand_keypoints_list


def safe_get_keypoint(hand_keypoints, idx):
    """安全获取关键点，避免索引越界"""
    if idx < len(hand_keypoints):
        kpt = hand_keypoints[idx]
        if kpt[2] > CONF_THRESHOLD:
            return kpt
    # 索引越界或置信度不足时返回默认值
    return np.array([0, 0, 0])


def recognize_hand_action(hand_keypoints):
    """识别手部细节动作，增加边界检查"""
    wrist = safe_get_keypoint(hand_keypoints, HAND_KEYPOINTS["wrist"])
    if wrist[2] < CONF_THRESHOLD:
        return "unknown"

    # 安全获取各指尖关键点
    wrist_coords = np.array([wrist[0], wrist[1]])
    thumb_tip = safe_get_keypoint(hand_keypoints, HAND_KEYPOINTS["thumb4"])
    index_tip = safe_get_keypoint(hand_keypoints, HAND_KEYPOINTS["index4"])
    middle_tip = safe_get_keypoint(hand_keypoints, HAND_KEYPOINTS["middle4"])
    ring_tip = safe_get_keypoint(hand_keypoints, HAND_KEYPOINTS["ring4"])
    pinky_tip = safe_get_keypoint(hand_keypoints, HAND_KEYPOINTS["pinky4"])

    # 计算归一化距离（增加除零保护）
    palm_base = safe_get_keypoint(hand_keypoints, HAND_KEYPOINTS["thumb1"])
    palm_dist = distance.euclidean(wrist_coords, [palm_base[0], palm_base[1]])
    if palm_dist < 5:  # 距离过小时直接返回unknown
        return "unknown"

    # 安全计算各手指距离
    thumb_dist = distance.euclidean(wrist_coords, [thumb_tip[0], thumb_tip[1]]) / palm_dist if thumb_tip[
                                                                                                   2] > CONF_THRESHOLD else 0
    index_dist = distance.euclidean(wrist_coords, [index_tip[0], index_tip[1]]) / palm_dist if index_tip[
                                                                                                   2] > CONF_THRESHOLD else 0
    middle_dist = distance.euclidean(wrist_coords, [middle_tip[0], middle_tip[1]]) / palm_dist if middle_tip[
                                                                                                      2] > CONF_THRESHOLD else 0
    ring_dist = distance.euclidean(wrist_coords, [ring_tip[0], ring_tip[1]]) / palm_dist if ring_tip[
                                                                                                2] > CONF_THRESHOLD else 0
    pinky_dist = distance.euclidean(wrist_coords, [pinky_tip[0], pinky_tip[1]]) / palm_dist if pinky_tip[
                                                                                                   2] > CONF_THRESHOLD else 0

    # 识别动作（仅基于有效关键点）
    extended_fingers = []
    if thumb_dist > ACTION_THRESHOLDS["thumb_up"]:
        extended_fingers.append("thumb")
    if index_dist > ACTION_THRESHOLDS["index_extended"]:
        extended_fingers.append("index")
    if middle_dist > ACTION_THRESHOLDS["open_hand"]:
        extended_fingers.append("middle")
    if ring_dist > ACTION_THRESHOLDS["open_hand"]:
        extended_fingers.append("ring")
    if pinky_dist > ACTION_THRESHOLDS["open_hand"]:
        extended_fingers.append("pinky")

    # 动作判断
    if len(extended_fingers) == 0:
        return "fist"
    elif len(extended_fingers) >= 4:
        return "open_hand"
    elif len(extended_fingers) == 1 and extended_fingers[0] == "thumb":
        return "thumb_up"
    elif len(extended_fingers) == 1 and extended_fingers[0] == "index":
        return "index_extended"
    else:
        return "unknown"


def draw_hand_details(frame, hand_type, hand_keypoints, action_label):
    """绘制手部细节，增加索引检查"""
    annotated_frame = frame.copy()

    # 遍历关键点，仅绘制有效索引
    for name, idx in HAND_KEYPOINTS.items():
        if idx >= len(hand_keypoints):
            continue  # 跳过越界索引
        kpt = hand_keypoints[idx]
        if kpt[2] > CONF_THRESHOLD:
            x, y = int(kpt[0]), int(kpt[1])
            # 匹配手指颜色
            finger_type = name.split("1")[0] if "1" in name else name.split("2")[0] if "2" in name else name.split("3")[
                0] if "3" in name else name.split("4")[0] if "4" in name else name
            color = KEYPOINT_COLORS.get(finger_type, (255, 255, 255))
            cv2.circle(annotated_frame, (x, y), 6, color, -1)
            cv2.circle(annotated_frame, (x, y), 8, (0, 0, 0), 2)

    # 绘制动作标签
    wrist = safe_get_keypoint(hand_keypoints, HAND_KEYPOINTS["wrist"])
    if wrist[2] > CONF_THRESHOLD:
        x, y = int(wrist[0]), int(wrist[1]) - 20
        label = f"{hand_type} hand: {action_label}"
        cv2.putText(
            annotated_frame, label, (x, y),
            cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 3
        )

    return annotated_frame


# -------------------------- 异步帧接收 --------------------------
async def receive_frames_async(websocket):
    global last_recv_time
    while True:
        try:
            last_recv_time = time.time_ns()
            frame_data = await websocket.recv()
            nparr = np.frombuffer(frame_data, np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if frame is not None:
                yield frame
        except Exception as e:
            print(f"⚠️ 帧接收异常: {e}")
            continue


# -------------------------- 主程序（仅保留单个窗口） --------------------------
async def main():
    global latency_list, last_resolution_switch
    # 仅创建一个自定义窗口（核心修复：移除YOLO自带窗口）
    window_name = "Hand Detail Action Recognition"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL | cv2.WINDOW_GUI_EXPANDED)
    cv2.resizeWindow(window_name, 1280, 720)
    # 强制设置窗口为前台，避免隐藏
    cv2.setWindowProperty(window_name, cv2.WND_PROP_TOPMOST, 1)

    fps = 0
    fps_start = cv2.getTickCount()
    frame_count = 0

    try:
        async with websockets.connect(
                WS_SERVER_URL,
                ping_interval=None,
                max_size=None,
                compression=None
        ) as websocket:
            print(f"\n✅ 成功连接服务器: {WS_SERVER_URL}")
            print("📌 操作说明：按q退出 | 按s切换分辨率（1280↔1920）")
            print(f"✅ 手部细节动作识别模式已启动 | 目标延迟≤{MAX_LATENCY}ms")

            async for frame in receive_frames_async(websocket):
                infer_start = time.time_ns()

                # 1. 推理获取Pose结果（不调用plot()，避免生成多余窗口）
                results = model(frame, **infer_kwargs)

                # 2. 提取手部关键点（带边界检查）
                hand_keypoints_list = extract_hand_keypoints(results)

                # 3. 识别手部细节动作并绘制（仅在自定义帧上绘制，不生成新窗口）
                annotated_frame = frame.copy()
                for hand_type, hand_kpts in hand_keypoints_list:
                    action = recognize_hand_action(hand_kpts)
                    annotated_frame = draw_hand_details(annotated_frame, hand_type, hand_kpts, action)

                # 4. 延迟统计（平滑计算）
                latency = (time.time_ns() - last_recv_time) / 1_000_000
                latency_list.append(latency)
                if len(latency_list) > 10:
                    latency_list.pop(0)
                avg_latency = np.mean(latency_list)

                # 5. 绘制帧率+延迟信息（仅在自定义窗口显示）
                cv2.putText(
                    annotated_frame,
                    f"FPS: {fps:.1f}/{TARGET_FPS} | Latency: {latency:.1f}ms (Avg: {avg_latency:.1f}ms)",
                    (20, 40), cv2.FONT_HERSHEY_SIMPLEX,
                    1.2, (0, 255, 0) if avg_latency <= MAX_LATENCY else (0, 0, 255), 3
                )

                # 6. 仅在唯一的自定义窗口显示（核心：避免多个imshow）
                cv2.imshow(window_name, annotated_frame)

                # 7. 帧率计算+优化的分辨率切换逻辑
                frame_count += 1
                current_time = time.time()
                if frame_count % 10 == 0:
                    fps_end = cv2.getTickCount()
                    fps = (10 * cv2.getTickFrequency()) / (fps_end - fps_start)
                    fps_start = fps_end

                    # 延迟滞后+时间间隔保护，避免频繁切换
                    if (avg_latency > MAX_LATENCY + LATENCY_HYSTERESIS and
                            infer_kwargs["imgsz"] == 1920 and
                            current_time - last_resolution_switch > 5):
                        infer_kwargs["imgsz"] = 1280
                        last_resolution_switch = current_time
                        print(f"🔄 延迟超标（{avg_latency:.1f}ms>55ms），分辨率降至1280×720")
                    elif (avg_latency < MAX_LATENCY - LATENCY_HYSTERESIS and
                          infer_kwargs["imgsz"] == 1280 and
                          current_time - last_resolution_switch > 5):
                        infer_kwargs["imgsz"] = 1920
                        last_resolution_switch = current_time
                        print(f"🔄 延迟正常（{avg_latency:.1f}ms<45ms），分辨率升至1920×1080")

                # 8. 按键控制
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q'):
                    print("\n👋 用户手动退出")
                    break
                elif key == ord('s'):
                    infer_kwargs["imgsz"] = 1920 if infer_kwargs["imgsz"] == 1280 else 1280
                    last_resolution_switch = current_time
                    res_text = "1920×1080" if infer_kwargs["imgsz"] == 1920 else "1280×720"
                    print(f"🔄 分辨率切换为: {res_text}")

                # 9. 帧率控速
                await asyncio.sleep(max(0, 1 / TARGET_FPS - (time.time_ns() - infer_start) / 1_000_000_000))

    except websockets.exceptions.ConnectionClosed:
        print("\n❌ 与树莓派的连接已断开")
    except Exception as e:
        print(f"\n❌ 程序异常: {e}")
        import traceback
        traceback.print_exc()  # 打印详细错误栈，方便排查
    finally:
        # 仅销毁唯一的自定义窗口
        cv2.destroyWindow(window_name)
        cv2.waitKey(1)  # 确保窗口彻底关闭
        torch.cuda.empty_cache()
        if latency_list:
            print(f"\n✅ 资源已清理 | 最终平均延迟: {np.mean(latency_list):.1f}ms | 最终帧率: {fps:.1f}FPS")
        else:
            print(f"\n✅ 资源已清理 | 最终帧率: {fps:.1f}FPS")


# -------------------------- 启动程序 --------------------------
if __name__ == "__main__":
    try:
        import nest_asyncio

        nest_asyncio.apply()
    except ImportError:
        pass

    asyncio.run(main())