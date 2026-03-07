from __future__ import annotations

import base64
import json
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple



@dataclass
class ExpertEvent:
    event_id: str
    event_name: str
    detected_classes: str
    timestamp: float
    frame: Any
    capture_metrics: Dict[str, Any]


@dataclass
class ExpertResult:
    event_id: str
    text: str
    severity: str = "warning"
    speak: bool = True
    source: str = "pc_expert_system"


def parse_pi_expert_packet(packet: str) -> Tuple[Optional[ExpertEvent], Optional[str]]:
    """解析 PI 端上报事件。

    支持格式:
    - PI_EXPERT_EVENT:{json_meta}:{base64_jpeg}
    - PI_YOLO_EVENT:{json_meta}:{base64_jpeg}
    """
    if not packet.startswith("PI_EXPERT_EVENT:") and not packet.startswith("PI_YOLO_EVENT:"):
        return None, "unsupported prefix"

    try:
        payload = packet.split(":", 1)[1]
        meta_raw, b64_img = payload.rsplit(":", 1)
        meta = json.loads(meta_raw)

        # 延迟导入，避免未安装视觉依赖时影响纯协议逻辑
        import numpy as np
        import cv2

        image_bytes = base64.b64decode(b64_img)
        arr = np.frombuffer(image_bytes, np.uint8)
        frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if frame is None:
            return None, "failed to decode frame"

        event_id = str(meta.get("event_id") or uuid.uuid4())
        return ExpertEvent(
            event_id=event_id,
            event_name=meta.get("event_name", "未知事件"),
            detected_classes=meta.get("detected_classes", ""),
            timestamp=float(meta.get("timestamp", 0.0)),
            frame=frame,
            capture_metrics=meta.get("capture_metrics", {}) if isinstance(meta, dict) else {},
        ), None
    except Exception as exc:
        return None, str(exc)


def build_expert_result_command(result: ExpertResult) -> str:
    body: Dict[str, Any] = {
        "event_id": result.event_id,
        "text": result.text,
        "severity": result.severity,
        "speak": result.speak,
        "source": result.source,
    }
    return f"CMD:EXPERT_RESULT:{json.dumps(body, ensure_ascii=False)}"


def parse_pi_expert_ack(packet: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    if not packet.startswith("PI_EXPERT_ACK:"):
        return None, "unsupported prefix"
    try:
        raw = packet.replace("PI_EXPERT_ACK:", "", 1)
        return json.loads(raw), None
    except Exception as exc:
        return None, str(exc)
