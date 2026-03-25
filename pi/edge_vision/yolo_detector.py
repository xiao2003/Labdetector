# pi/edge_vision/yolo_detector.py
from __future__ import annotations

import time
from pathlib import Path

from ultralytics import YOLO
from .policy_engine import apply_policies_to_detections

try:
    from ..config import get_pi_config
except ImportError:  # pragma: no cover - direct script fallback
    from config import get_pi_config


class SemanticEdgeEngine:
    def __init__(self) -> None:
        weights_path = str(get_pi_config("detector.weights_path", "yolov8n.pt") or "yolov8n.pt")
        conf = float(get_pi_config("detector.conf", 0.4) or 0.4)
        imgsz = int(get_pi_config("detector.imgsz", 640) or 640)
        self.conf = max(0.05, min(conf, 0.95))
        self.imgsz = max(320, min(imgsz, 1280))
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
        返回触发的事件列表:
        [(event_name, image_to_send, detected_classes_str, policy_meta), ...]
        """
        if not policies:
            return []

        # 在树莓派 5 上显式传入 imgsz，避免默认推理尺寸失控导致负载飘高。
        results = self.model(frame, verbose=False, conf=self.conf, imgsz=self.imgsz)
        detected_objects = []
        boxes_dict = {}

        for result in results:
            for box in result.boxes:
                cls_name = self.model.names[int(box.cls[0])]
                detected_objects.append(cls_name)
                boxes_dict.setdefault(cls_name, []).append(list(map(int, box.xyxy[0])))
        return apply_policies_to_detections(
            frame,
            policies,
            detected_objects,
            boxes_dict,
            last_triggers=self.last_triggers,
            current_time=time.time(),
        )


class GeneralYoloDetector:
    """兼容旧调用方式的策略驱动检测器封装。"""

    def __init__(self) -> None:
        self.engine = SemanticEdgeEngine()

    def process_frame(self, frame, policies):
        return self.engine.process_frame(frame, policies)
