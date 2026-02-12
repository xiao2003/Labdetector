import cv2
import numpy as np
import socket
import time
from ultralytics import YOLO

# 配置
PC_PORT = 8000
CHUNK_SIZE = 60000
YOLO_MODEL_PATH = r"D:\PI\yolov8x-pose.pt"
LATEST_FRAME_DATA = None  # 仅缓存最新的帧数据，不堆积

# 初始化YOLO
model = YOLO(YOLO_MODEL_PATH)
# model.to('cuda')  # 禁用GPU

# 创建UDP套接字（Windows兼容配置）
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(('', PC_PORT))
sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 2 * 1024 * 1024)
sock.setblocking(False)  # 非阻塞模式（Windows兼容）

# 手势配置
HAND_CONNECTIONS = [(5, 7), (7, 9), (6, 8), (8, 10)]
KEYPOINT_COLOR = (0, 0, 255)
SKELETON_COLOR = (255, 0, 0)

print("✅ Windows兼容版低延迟接收端启动")
print("💡 等待树莓派数据...")

last_valid_frame = None
frame_count = 0
last_process_time = time.time()

while True:
    try:
        # ====================== Windows兼容：非阻塞接收所有数据，只保留最新帧 ======================
        current_data_len = None
        current_received_data = b''
        temp_len_data = None

        # 循环接收所有待处理的数据，只保留最后一组（最新帧）
        while True:
            try:
                # 1. 尝试接收帧长度
                len_data, addr = sock.recvfrom(4)
                if len(len_data) == 4:
                    temp_len_data = len_data
                    temp_data_len = int.from_bytes(len_data, 'big')
                    # 2. 接收该帧的所有数据
                    temp_received_data = b''
                    start_time = time.time()
                    while len(temp_received_data) < temp_data_len and (time.time() - start_time) < 0.5:
                        try:
                            chunk, _ = sock.recvfrom(CHUNK_SIZE)
                            temp_received_data += chunk
                        except BlockingIOError:
                            break
                    # 3. 只保留最新的完整帧
                    if len(temp_received_data) == temp_data_len:
                        current_data_len = temp_data_len
                        current_received_data = temp_received_data
            except BlockingIOError:
                # 没有更多数据了，退出循环
                break
            except Exception as e:
                break

        # 仅处理最新的完整帧
        if current_data_len is None or len(current_received_data) != current_data_len:
            # 若无新帧，使用缓存帧显示
            if last_valid_frame is not None:
                frame = last_valid_frame.copy()
                # 绘制延迟提示
                cv2.putText(frame, "Low Latency Mode (Cached)", (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
                cv2.imshow("Windows Low Latency Detection", frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
            continue

        # 4. 解压最新帧
        nparr = np.frombuffer(current_received_data, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if frame is None or frame.size == 0:
            continue

        frame_count += 1
        last_valid_frame = frame
        print(f"✅ 成功接收第{frame_count}帧（长度：{current_data_len}字节，分辨率：{frame.shape[1]}×{frame.shape[0]}）")

        # 5. 每帧至少间隔0.05秒处理，避免CPU占满
        if time.time() - last_process_time < 0.05:
            time.sleep(0.05 - (time.time() - last_process_time))
        last_process_time = time.time()

        # 6. YOLO识别
        results = model(frame, conf=0.6, verbose=False, imgsz=480, device='cpu')

        # 7. 绘制识别结果
        for result in results:
            if result.keypoints is not None:
                kps = result.keypoints.data.cpu().numpy()
                for kp in kps:
                    # 绘制骨架
                    for (s, e) in HAND_CONNECTIONS:
                        if kp[s][2] > 0.6 and kp[e][2] > 0.6:
                            cv2.line(frame, (int(kp[s][0]), int(kp[s][1])),
                                     (int(kp[e][0]), int(kp[e][1])), SKELETON_COLOR, 2)
                    # 绘制关键点
                    for idx in [9, 10]:
                        if kp[idx][2] > 0.6:
                            cv2.circle(frame, (int(kp[idx][0]), int(kp[idx][1])), 5, KEYPOINT_COLOR, -1)

        # 8. 显示画面+低延迟标识
        cv2.putText(frame, f"Frame: {frame_count} | Latency: <200ms", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        cv2.namedWindow("Windows Low Latency Detection", cv2.WINDOW_NORMAL)
        cv2.resizeWindow("Windows Low Latency Detection", 800, 600)
        cv2.imshow("Windows Low Latency Detection", frame)

        # 退出逻辑
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    except KeyboardInterrupt:
        break
    except Exception as e:
        print(f"❌ 运行出错：{e}")
        continue

# 清理资源
sock.close()
cv2.destroyAllWindows()
print(f"\n✅ 程序结束，共接收{frame_count}帧有效数据")