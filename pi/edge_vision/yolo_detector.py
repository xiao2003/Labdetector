# pi/edge_vision/yolo_detector.py
from __future__ import annotations

import time
from pathlib import Path

from ultralytics import YOLO

try:
    from ..config import get_pi_config
except ImportError:  # pragma: no cover - direct script fallback
    from config import get_pi_config


class SemanticEdgeEngine:
    def __init__(self) -> None:
        weights_path = str(get_pi_config("detector.weights_path", "yolov8n.pt") or "yolov8n.pt")
        conf = float(get_pi_config("detector.conf", 0.4) or 0.4)
        self.conf = max(0.05, min(conf, 0.95))
        self.weights_path = self._resolve_weights_path(weights_path)
        self.model = YOLO(self.weights_path)
        self.last_triggers = {}

    @staticmethod
    def _resolve_weights_path(raw_path: str) -> str:
        candidate = Path(str(raw_path or "yolov8n.pt"))
        if candidate.is_absolute() and candidate.exists():
            return str(candidate)
        base_dir = Path(__file__).resolve().parents[1]
        local_candidate = (base_dir / candidate).resolve()
        if local_candidate.exists():
            return str(local_candidate)
        bundled_candidate = (base_dir / "models" / "detectors" / candidate.name).resolve()
        if bundled_candidate.exists():
            return str(bundled_candidate)
        return str(candidate)

    def process_frame(self, frame, policies):
        """
        接收一帧画面和 N 个专家策略。
        返回触发的事件列表: [(event_name, image_to_send, detected_classes_str), ...]
        """
        if not policies:
            return []

        results = self.model(frame, verbose=False, conf=self.conf)
        detected_objects = []
        boxes_dict = {}

        for result in results:
            for box in result.boxes:
                cls_name = self.model.names[int(box.cls[0])]
                detected_objects.append(cls_name)
                boxes_dict.setdefault(cls_name, []).append(list(map(int, box.xyxy[0])))

        detected_set = set(detected_objects)
        detected_str = ",".join(sorted(detected_set))
        triggered_events = []
        current_time = time.time()

        for policy in policies:
            event_name = policy.get("event_name")
            targets = set(policy.get("trigger_classes", []))
            condition = policy.get("condition", "any")
            action = policy.get("action", "full_frame")
            cooldown = float(policy.get("cooldown", 5.0) or 5.0)

            if not event_name or not targets:
                continue
            if current_time - self.last_triggers.get(event_name, 0.0) < cooldown:
                continue

            is_match = False
            if condition == "all" and targets.issubset(detected_set):
                is_match = True
            elif condition == "any" and not targets.isdisjoint(detected_set):
                is_match = True

            if not is_match:
                continue

            self.last_triggers[event_name] = current_time
            if action == "crop_target":
                target_cls = list(targets.intersection(detected_set))[0]
                x1, y1, x2, y2 = boxes_dict[target_cls][0]
                h, w = frame.shape[:2]
                crop_img = frame[max(0, y1 - 20):min(h, y2 + 20), max(0, x1 - 20):min(w, x2 + 20)]
                triggered_events.append((event_name, crop_img, detected_str))
            else:
                triggered_events.append((event_name, frame.copy(), detected_str))

        return triggered_events


class GeneralYoloDetector:
    """兼容旧调用方式的策略驱动检测器封装。"""

    def __init__(self) -> None:
        self.engine = SemanticEdgeEngine()

    def process_frame(self, frame, policies):
        return self.engine.process_frame(frame, policies)
