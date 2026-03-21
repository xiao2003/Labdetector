from __future__ import annotations

import base64
import json
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Sequence

import cv2
import numpy as np

from pi.edge_vision.policy_engine import apply_policies_to_detections


@dataclass
class SimulatedDetectionScenario:
    event_name: str
    frame: Any
    detected_objects: Sequence[str]
    boxes_dict: Dict[str, List[List[int]]]
    capture_metrics: Dict[str, Any]


class PiClosedLoopBridge:
    """Reuse pi-side policy logic for virtual closed-loop tests."""

    def __init__(self) -> None:
        self.last_triggers: Dict[str, float] = {}

    def trigger_events(
        self,
        frame: Any,
        policies: Sequence[Dict[str, Any]],
        detected_objects: Sequence[str],
        boxes_dict: Dict[str, List[List[int]]],
    ) -> List[tuple[str, Any, str, Dict[str, Any]]]:
        return apply_policies_to_detections(
            frame,
            policies,
            list(detected_objects),
            dict(boxes_dict),
            last_triggers=self.last_triggers,
            current_time=time.time(),
        )

    def build_event_packets(
        self,
        triggered_events: Iterable[tuple[str, Any, str, Dict[str, Any]]],
        *,
        capture_metrics: Dict[str, Any],
        jpeg_quality: int = 88,
    ) -> List[str]:
        packets: List[str] = []
        for event_name, event_frame, detected_str, policy_meta in triggered_events:
            ok, buf = cv2.imencode(".jpg", event_frame, [int(cv2.IMWRITE_JPEG_QUALITY), int(jpeg_quality)])
            if not ok:
                continue
            b64_img = base64.b64encode(buf.tobytes()).decode("utf-8")
            payload = {
                "event_id": str(uuid.uuid4()),
                "event_name": event_name,
                "expert_code": str((policy_meta or {}).get("expert_code", "") or ""),
                "policy_name": str((policy_meta or {}).get("policy_name", event_name) or event_name),
                "policy_action": str((policy_meta or {}).get("policy_action", "") or ""),
                "detected_classes": detected_str,
                "timestamp": time.time(),
                "capture_metrics": dict(capture_metrics or {}),
            }
            packets.append(f"PI_EXPERT_EVENT:{json.dumps(payload, ensure_ascii=False)}:{b64_img}")
        return packets


def default_simulated_scenarios(node_id: str = "1") -> List[SimulatedDetectionScenario]:
    chem_frame = np.full((540, 960, 3), 245, dtype=np.uint8)
    cv2.rectangle(chem_frame, (90, 90), (860, 470), (42, 62, 88), 3)
    cv2.putText(chem_frame, f"Virtual Pi {node_id}", (120, 130), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (20, 20, 20), 3, cv2.LINE_AA)
    cv2.putText(chem_frame, "HF", (400, 280), cv2.FONT_HERSHEY_SIMPLEX, 4.8, (0, 0, 0), 12, cv2.LINE_AA)
    cv2.putText(chem_frame, "Wear gloves", (300, 390), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (10, 10, 10), 4, cv2.LINE_AA)

    ppe_frame = np.full((540, 960, 3), 250, dtype=np.uint8)
    cv2.rectangle(ppe_frame, (110, 70), (850, 500), (40, 60, 90), 3)
    cv2.putText(ppe_frame, f"Virtual Pi {node_id}", (120, 120), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (20, 20, 20), 3, cv2.LINE_AA)
    cv2.putText(ppe_frame, "Operator", (330, 220), cv2.FONT_HERSHEY_SIMPLEX, 2.2, (0, 0, 0), 5, cv2.LINE_AA)
    cv2.putText(ppe_frame, "No coat / gloves / goggles", (180, 340), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 80, 170), 3, cv2.LINE_AA)

    return [
        SimulatedDetectionScenario(
            event_name="危化品识别",
            frame=chem_frame,
            detected_objects=["bottle", "hf_label", "person"],
            boxes_dict={
                "bottle": [[260, 130, 730, 455]],
                "hf_label": [[320, 150, 690, 420]],
                "person": [[120, 90, 850, 500]],
            },
            capture_metrics={
                "source": "virtual_pi_bridge",
                "scenario": "chem",
                "node_id": node_id,
            },
        ),
        SimulatedDetectionScenario(
            event_name="PPE穿戴检查",
            frame=ppe_frame,
            detected_objects=["person", "no_lab_coat", "no_gloves", "no_goggles"],
            boxes_dict={
                "person": [[190, 90, 760, 470]],
                "no_lab_coat": [[260, 170, 690, 430]],
                "no_gloves": [[250, 280, 700, 440]],
                "no_goggles": [[330, 160, 620, 250]],
            },
            capture_metrics={
                "source": "virtual_pi_bridge",
                "scenario": "ppe",
                "node_id": node_id,
            },
        ),
    ]
