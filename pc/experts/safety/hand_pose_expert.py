from __future__ import annotations

import importlib
import json
import math
from typing import Any, Dict, List, Optional

from pc.core.base_expert import BaseExpert


class HandPoseExpert(BaseExpert):
    """Hand pose expert for high-precision lab action capture."""

    _FINGER_SPECS = {
        "thumb": {"root": 2, "tip": 4},
        "index": {"root": 5, "tip": 8},
        "middle": {"root": 9, "tip": 12},
        "ring": {"root": 13, "tip": 16},
        "pinky": {"root": 17, "tip": 20},
    }

    @property
    def expert_name(self) -> str:
        return "手部姿态估计专家"

    @property
    def expert_version(self) -> str:
        return "3.0.2"

    def supported_events(self) -> List[str]:
        return [
            "hand_pose_analysis",
            "hand_pose_estimation",
            "gesture_analysis",
            "手部姿态估计",
            "手势分析",
        ]

    def get_edge_policy(self) -> Dict[str, Any]:
        return {
            "event_name": "hand_pose_analysis",
            "trigger_classes": ["person", "hand", "glove"],
            "condition": "any",
            "action": "full_frame",
            "cooldown": 1.5,
        }

    def match_event(self, event_name: str) -> bool:
        normalized = (event_name or "").strip().lower()
        return normalized in {item.lower() for item in self.supported_events()}

    def analyze(self, frame: Any, context: dict) -> str:
        if frame is None:
            return self._dump_result(hand_status="no_frame", reason="empty_frame")

        try:
            cv2 = importlib.import_module("cv2")
            mp = importlib.import_module("mediapipe")
        except Exception:
            return self._dump_result(hand_status="dependency_missing", reason="mediapipe_or_cv2_unavailable")

        hands = mp.solutions.hands.Hands(
            static_image_mode=bool(context.get("static_image_mode", False)),
            max_num_hands=int(context.get("max_num_hands", 2)),
            model_complexity=int(context.get("model_complexity", 1)),
            min_detection_confidence=float(context.get("min_detection_confidence", 0.6)),
            min_tracking_confidence=float(context.get("min_tracking_confidence", 0.5)),
        )

        try:
            image_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = hands.process(image_rgb)
        finally:
            hands.close()

        if not results.multi_hand_landmarks:
            return self._dump_result(hand_status="no_hand", reason="no_hand_detected")

        width = int(getattr(frame, "shape", [0, 0])[1] or 0)
        height = int(getattr(frame, "shape", [0, 0])[0] or 0)
        hand_summaries = []

        for index, hand_landmarks in enumerate(results.multi_hand_landmarks):
            handedness = self._resolve_handedness(results, index)
            summary = self._analyze_single_hand(hand_landmarks.landmark, width, height, handedness)
            hand_summaries.append(summary)

        primary = hand_summaries[0]
        response = {
            "hand_status": primary["hand_status"],
            "keypoints": primary["keypoints"],
            "hands": hand_summaries,
            "summary": {
                "extended_fingers": primary["extended_fingers"],
                "curled_fingers": primary["curled_fingers"],
                "handedness": primary["handedness"],
            },
        }
        return json.dumps(response, ensure_ascii=False)

    def _analyze_single_hand(self, landmarks: List[Any], width: int, height: int, handedness: str) -> Dict[str, Any]:
        wrist = self._point_dict("wrist", landmarks[0], width, height)
        palm_scale = self._estimate_palm_scale(landmarks)
        finger_states = {}
        keypoints = [wrist]

        extended_count = 0
        curled_count = 0

        for finger_name, spec in self._FINGER_SPECS.items():
            root_landmark = landmarks[spec["root"]]
            tip_landmark = landmarks[spec["tip"]]
            root_point = self._point_dict(f"{finger_name}_root", root_landmark, width, height)
            tip_point = self._point_dict(f"{finger_name}_tip", tip_landmark, width, height)
            keypoints.extend([root_point, tip_point])

            root_distance = self._normalized_distance(landmarks[0], root_landmark, palm_scale)
            tip_distance = self._normalized_distance(landmarks[0], tip_landmark, palm_scale)
            root_tip_distance = self._normalized_distance(root_landmark, tip_landmark, palm_scale)
            extension_ratio = tip_distance / max(root_distance, 1e-6)
            is_extended = extension_ratio >= (1.55 if finger_name == "thumb" else 1.8) and root_tip_distance >= 0.55

            finger_states[finger_name] = {
                "extended": is_extended,
                "normalized_root_distance": round(root_distance, 4),
                "normalized_tip_distance": round(tip_distance, 4),
                "normalized_root_tip_distance": round(root_tip_distance, 4),
                "extension_ratio": round(extension_ratio, 4),
            }
            if is_extended:
                extended_count += 1
            else:
                curled_count += 1

        hand_status = self._classify_hand_status(finger_states, extended_count, curled_count)
        return {
            "hand_status": hand_status,
            "handedness": handedness,
            "extended_fingers": extended_count,
            "curled_fingers": curled_count,
            "finger_states": finger_states,
            "keypoints": keypoints,
        }

    def _classify_hand_status(self, finger_states: Dict[str, Dict[str, Any]], extended_count: int, curled_count: int) -> str:
        if curled_count >= 4:
            return "holding"
        if extended_count >= 4:
            return "open"
        if finger_states["index"]["extended"] and extended_count == 1:
            return "pointing"
        if finger_states["thumb"]["extended"] and finger_states["index"]["extended"] and curled_count >= 2:
            return "pinching"
        return "partial_open"

    def _estimate_palm_scale(self, landmarks: List[Any]) -> float:
        wrist = landmarks[0]
        scales = [
            self._euclidean_distance(wrist, landmarks[5]),
            self._euclidean_distance(wrist, landmarks[9]),
            self._euclidean_distance(wrist, landmarks[13]),
            self._euclidean_distance(wrist, landmarks[17]),
        ]
        valid = [value for value in scales if value > 0]
        return sum(valid) / max(len(valid), 1)

    def _normalized_distance(self, start: Any, end: Any, scale: float) -> float:
        return self._euclidean_distance(start, end) / max(scale, 1e-6)

    def _euclidean_distance(self, start: Any, end: Any) -> float:
        return math.sqrt(
            (float(start.x) - float(end.x)) ** 2
            + (float(start.y) - float(end.y)) ** 2
            + (float(getattr(start, "z", 0.0)) - float(getattr(end, "z", 0.0))) ** 2
        )

    def _point_dict(self, name: str, landmark: Any, width: int, height: int) -> Dict[str, Any]:
        return {
            "name": name,
            "x": round(float(landmark.x), 6),
            "y": round(float(landmark.y), 6),
            "z": round(float(getattr(landmark, "z", 0.0)), 6),
            "pixel_x": int(float(landmark.x) * width) if width else None,
            "pixel_y": int(float(landmark.y) * height) if height else None,
        }

    def _resolve_handedness(self, results: Any, index: int) -> str:
        handedness_list: Optional[List[Any]] = getattr(results, "multi_handedness", None)
        if not handedness_list or index >= len(handedness_list):
            return "unknown"
        try:
            return str(handedness_list[index].classification[0].label).lower()
        except Exception:
            return "unknown"

    def _dump_result(self, hand_status: str, reason: str) -> str:
        return json.dumps({"hand_status": hand_status, "keypoints": [], "reason": reason}, ensure_ascii=False)
