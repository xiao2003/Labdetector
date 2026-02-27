# piside/edge_vision/yolo_detector.py
import time

try:
    from ultralytics import YOLO
except ImportError:
    print("[WARN] 未检测到 ultralytics，请先 pip install ultralytics")


class GeneralYoloDetector:
    def __init__(self, model_path="yolov8n.pt", conf_thres=0.4, cooldown=10.0):
        self.conf_thres = conf_thres
        self.cooldown = cooldown
        self.last_trigger_time = 0

        # 直接加载 pt 原生模型
        try:
            self.model = YOLO(model_path)
        except Exception as e:
            print(f"模型加载失败: {e}")
            self.model = None

    def process_frame(self, frame):
        if self.model is None:
            return False, ""

        current_time = time.time()
        if current_time - self.last_trigger_time < self.cooldown:
            return False, ""

        # 直接推理
        results = self.model(frame, verbose=False, conf=self.conf_thres)

        detected_objects = []
        for r in results:
            for box in r.boxes:
                class_id = int(box.cls[0])
                class_name = self.model.names[class_id]
                detected_objects.append(class_name)

        # 同样模拟测试：如果画面有人(person)且有手机(cell phone)
        if "person" in detected_objects and "cell phone" in detected_objects:
            self.last_trigger_time = current_time
            return True, "安防违规-在实验台使用手机"  # 直接作为 event_name

        return False, ""