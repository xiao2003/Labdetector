# piside/edge_vision/yolo_detector.py
import time
from ultralytics import YOLO


class SemanticEdgeEngine:
    def __init__(self):
        self.model = YOLO("yolov8n.pt")  # 通用感知器
        self.last_triggers = {}

    def process_frame(self, frame, policies):
        """
        接收一帧画面和 N 个专家的策略。
        返回触发的事件列表: [(event_name, image_to_send, detected_classes_str), ...]
        """
        if not policies:
            return []

        # 1. 通用感知：YOLO 只跑一次，提取所有目标
        results = self.model(frame, verbose=False, conf=0.4)
        detected_objects = []
        boxes_dict = {}  # 记录每个类别的坐标框，方便裁剪

        for r in results:
            for box in r.boxes:
                cls_name = self.model.names[int(box.cls[0])]
                detected_objects.append(cls_name)
                # 记录坐标
                if cls_name not in boxes_dict:
                    boxes_dict[cls_name] = []
                boxes_dict[cls_name].append(list(map(int, box.xyxy[0])))

        detected_set = set(detected_objects)
        detected_str = ",".join(detected_set)  # 例如: "person,cell phone,bottle"

        triggered_events = []
        current_time = time.time()

        # 2. 规则路由：遍历 N 个专家的策略
        for policy in policies:
            event_name = policy.get("event_name")
            targets = set(policy.get("trigger_classes", []))
            condition = policy.get("condition", "any")
            action = policy.get("action", "full_frame")
            cooldown = policy.get("cooldown", 5.0)

            # 冷却检查
            if current_time - self.last_triggers.get(event_name, 0) < cooldown:
                continue

            # 匹配逻辑
            is_match = False
            if condition == "all" and targets.issubset(detected_set):
                is_match = True
            elif condition == "any" and not targets.isdisjoint(detected_set):
                is_match = True

            # 3. 执行动作 (全图 vs 裁剪)
            if is_match:
                self.last_triggers[event_name] = current_time

                if action == "crop_target":
                    # 找到触发的目标，进行画面裁剪 (以第一个找到的目标为例)
                    target_cls = list(targets.intersection(detected_set))[0]
                    x1, y1, x2, y2 = boxes_dict[target_cls][0]
                    # 向外扩张一点边缘
                    h, w = frame.shape[:2]
                    crop_img = frame[max(0, y1 - 20):min(h, y2 + 20), max(0, x1 - 20):min(w, x2 + 20)]
                    triggered_events.append((event_name, crop_img, detected_str))
                else:
                    # 回传全图
                    triggered_events.append((event_name, frame.copy(), detected_str))

        return triggered_events