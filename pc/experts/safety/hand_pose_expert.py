from __future__ import annotations

import importlib
import json
import math
import threading
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

from pc.app_identity import resource_path
from pc.core.base_expert import BaseExpert


_HAND_TASK_URL = (
    "https://storage.googleapis.com/mediapipe-models/"
    "hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
)
_HAND_TASK_PATH = Path(resource_path("pc/models/mediapipe/hand_landmarker.task"))
_GESTURE_TASK_URL = (
    "https://storage.googleapis.com/mediapipe-models/"
    "gesture_recognizer/gesture_recognizer/float16/1/gesture_recognizer.task"
)
_GESTURE_TASK_PATH = Path(resource_path("pc/models/mediapipe/gesture_recognizer.task"))
_TASKS_LOCK = threading.Lock()
_TASKS_LANDMARKER: Any = None
_TASKS_ERROR = ""
_TASKS_GESTURE_RECOGNIZER: Any = None
_TASKS_GESTURE_ERROR = ""


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
        return "3.0.3"

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
        except Exception:
            return self._dump_result(hand_status="dependency_missing", reason="cv2_unavailable")

        try:
            mp = importlib.import_module("mediapipe")
        except Exception:
            return self._dump_result(hand_status="dependency_missing", reason="mediapipe_unavailable")

        legacy_result = self._analyze_with_legacy_solutions(mp, cv2, frame, context)
        if legacy_result is not None:
            return legacy_result

        gesture_result = self._analyze_with_gesture_tasks(mp, cv2, frame, context)
        if gesture_result is not None:
            return gesture_result

        tasks_result = self._analyze_with_tasks(mp, cv2, frame, context)
        if tasks_result is not None:
            return tasks_result

        reason = _TASKS_GESTURE_ERROR or _TASKS_ERROR or "no_compatible_hand_backend"
        return self._dump_result(hand_status="dependency_missing", reason=reason)

    def _analyze_with_legacy_solutions(self, mp: Any, cv2: Any, frame: Any, context: dict) -> Optional[str]:
        solutions = getattr(mp, "solutions", None)
        hands_api = getattr(solutions, "hands", None) if solutions is not None else None
        if hands_api is None:
            return None

        hands = hands_api.Hands(
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
        return self._format_results(
            frame,
            [
                {
                    "landmarks": hand_landmarks.landmark,
                    "handedness": self._resolve_handedness(results, index),
                }
                for index, hand_landmarks in enumerate(results.multi_hand_landmarks)
            ],
        )

    def _analyze_with_tasks(self, mp: Any, cv2: Any, frame: Any, context: dict) -> Optional[str]:
        landmarker = self._get_tasks_landmarker(mp, context)
        if landmarker is None:
            return None

        image_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=image_rgb)
        try:
            result = landmarker.detect(mp_image)
        except Exception as exc:
            self._remember_tasks_error(f"tasks_detect_failed:{exc}")
            return self._dump_result(hand_status="error", reason=f"tasks_detect_failed:{exc}")

        hand_landmarks = getattr(result, "hand_landmarks", None) or []
        if not hand_landmarks:
            return self._dump_result(hand_status="no_hand", reason="no_hand_detected")

        handedness_rows = getattr(result, "handedness", None) or []
        formatted = []
        for index, landmarks in enumerate(hand_landmarks):
            handedness = "unknown"
            if index < len(handedness_rows):
                row = handedness_rows[index]
                if row:
                    candidate = row[0]
                    handedness = str(getattr(candidate, "category_name", "unknown") or "unknown").lower()
            formatted.append({"landmarks": landmarks, "handedness": handedness})
        return self._format_results(frame, formatted)

    def _analyze_with_gesture_tasks(self, mp: Any, cv2: Any, frame: Any, context: dict) -> Optional[str]:
        recognizer = self._get_tasks_gesture_recognizer(mp, context)
        if recognizer is None:
            return None

        image_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=image_rgb)
        try:
            result = recognizer.recognize(mp_image)
        except Exception as exc:
            self._remember_tasks_gesture_error(f"gesture_recognize_failed:{exc}")
            return None

        hand_landmarks = getattr(result, "hand_landmarks", None) or []
        if not hand_landmarks:
            return self._dump_result(hand_status="no_hand", reason="no_hand_detected")

        handedness_rows = getattr(result, "handedness", None) or []
        gesture_rows = getattr(result, "gestures", None) or []
        formatted = []
        for index, landmarks in enumerate(hand_landmarks):
            handedness = "unknown"
            if index < len(handedness_rows) and handedness_rows[index]:
                handedness = str(getattr(handedness_rows[index][0], "category_name", "unknown") or "unknown").lower()
            gesture_label = ""
            if index < len(gesture_rows) and gesture_rows[index]:
                gesture_label = str(getattr(gesture_rows[index][0], "category_name", "") or "")
            formatted.append(
                {
                    "landmarks": landmarks,
                    "handedness": handedness,
                    "gesture_label": self._map_gesture_label(gesture_label),
                }
            )
        return self._format_results(frame, formatted)

    def _get_tasks_landmarker(self, mp: Any, context: dict) -> Any:
        global _TASKS_LANDMARKER
        if _TASKS_LANDMARKER is not None:
            return _TASKS_LANDMARKER

        with _TASKS_LOCK:
            if _TASKS_LANDMARKER is not None:
                return _TASKS_LANDMARKER
            try:
                task_path = self._ensure_task_model()
                python_tasks = importlib.import_module("mediapipe.tasks.python")
                vision = importlib.import_module("mediapipe.tasks.python.vision")
                base_options = python_tasks.BaseOptions(model_asset_path=str(task_path))
                options = vision.HandLandmarkerOptions(
                    base_options=base_options,
                    running_mode=vision.RunningMode.IMAGE,
                    num_hands=int(context.get("max_num_hands", 2)),
                    min_hand_detection_confidence=float(context.get("min_detection_confidence", 0.6)),
                    min_hand_presence_confidence=float(context.get("min_tracking_confidence", 0.5)),
                    min_tracking_confidence=float(context.get("min_tracking_confidence", 0.5)),
                )
                _TASKS_LANDMARKER = vision.HandLandmarker.create_from_options(options)
                self._remember_tasks_error("")
                return _TASKS_LANDMARKER
            except Exception as exc:
                self._remember_tasks_error(f"tasks_init_failed:{exc}")
                return None

    def _get_tasks_gesture_recognizer(self, mp: Any, context: dict) -> Any:
        global _TASKS_GESTURE_RECOGNIZER
        if _TASKS_GESTURE_RECOGNIZER is not None:
            return _TASKS_GESTURE_RECOGNIZER

        with _TASKS_LOCK:
            if _TASKS_GESTURE_RECOGNIZER is not None:
                return _TASKS_GESTURE_RECOGNIZER
            try:
                task_path = self._ensure_gesture_task_model()
                python_tasks = importlib.import_module("mediapipe.tasks.python")
                vision = importlib.import_module("mediapipe.tasks.python.vision")
                base_options = python_tasks.BaseOptions(model_asset_path=str(task_path))
                options = vision.GestureRecognizerOptions(
                    base_options=base_options,
                    running_mode=vision.RunningMode.IMAGE,
                    num_hands=int(context.get("max_num_hands", 2)),
                    min_hand_detection_confidence=float(context.get("min_detection_confidence", 0.6)),
                    min_hand_presence_confidence=float(context.get("min_tracking_confidence", 0.5)),
                    min_tracking_confidence=float(context.get("min_tracking_confidence", 0.5)),
                )
                _TASKS_GESTURE_RECOGNIZER = vision.GestureRecognizer.create_from_options(options)
                self._remember_tasks_gesture_error("")
                return _TASKS_GESTURE_RECOGNIZER
            except Exception as exc:
                self._remember_tasks_gesture_error(f"gesture_tasks_init_failed:{exc}")
                return None

    def _ensure_task_model(self) -> Path:
        if _HAND_TASK_PATH.exists():
            return _HAND_TASK_PATH
        _HAND_TASK_PATH.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(_HAND_TASK_URL, _HAND_TASK_PATH)
        return _HAND_TASK_PATH

    def _ensure_gesture_task_model(self) -> Path:
        if _GESTURE_TASK_PATH.exists():
            return _GESTURE_TASK_PATH
        _GESTURE_TASK_PATH.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(_GESTURE_TASK_URL, _GESTURE_TASK_PATH)
        return _GESTURE_TASK_PATH

    def _remember_tasks_error(self, message: str) -> None:
        global _TASKS_ERROR
        _TASKS_ERROR = str(message or "")

    def _remember_tasks_gesture_error(self, message: str) -> None:
        global _TASKS_GESTURE_ERROR
        _TASKS_GESTURE_ERROR = str(message or "")

    def _format_results(self, frame: Any, detected_hands: List[Dict[str, Any]]) -> str:
        width = int(getattr(frame, "shape", [0, 0])[1] or 0)
        height = int(getattr(frame, "shape", [0, 0])[0] or 0)
        hand_summaries = []

        for hand in detected_hands:
            landmarks = hand["landmarks"]
            handedness = hand["handedness"]
            summary = self._analyze_single_hand(
                landmarks,
                width,
                height,
                handedness,
                hand.get("gesture_label", ""),
            )
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

    def _analyze_single_hand(
        self,
        landmarks: List[Any],
        width: int,
        height: int,
        handedness: str,
        gesture_label: str = "",
    ) -> Dict[str, Any]:
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

        hand_status = gesture_label or self._classify_hand_status(finger_states, extended_count, curled_count)
        return {
            "hand_status": hand_status,
            "handedness": handedness,
            "extended_fingers": extended_count,
            "curled_fingers": curled_count,
            "finger_states": finger_states,
            "keypoints": keypoints,
        }

    def _map_gesture_label(self, gesture_label: str) -> str:
        mapping = {
            "Open_Palm": "open",
            "Closed_Fist": "holding",
            "Pointing_Up": "pointing",
            "Victory": "victory",
            "Thumb_Up": "thumbs_up",
            "Thumb_Down": "thumbs_down",
            "ILoveYou": "call_me",
        }
        return mapping.get((gesture_label or "").strip(), "")

    def _classify_hand_status(self, finger_states: Dict[str, Dict[str, Any]], extended_count: int, curled_count: int) -> str:
        thumb = finger_states["thumb"]["extended"]
        index = finger_states["index"]["extended"]
        middle = finger_states["middle"]["extended"]
        ring = finger_states["ring"]["extended"]
        pinky = finger_states["pinky"]["extended"]
        thumb_ratio = float(finger_states["thumb"]["extension_ratio"])
        index_ratio = float(finger_states["index"]["extension_ratio"])
        middle_ratio = float(finger_states["middle"]["extension_ratio"])
        ring_ratio = float(finger_states["ring"]["extension_ratio"])
        pinky_ratio = float(finger_states["pinky"]["extension_ratio"])
        if extended_count >= 4:
            return "open"
        if (
            index
            and not middle
            and not ring
            and not pinky
            and index_ratio >= 1.7
            and middle_ratio < 1.1
            and ring_ratio < 1.05
            and pinky_ratio < 1.1
        ):
            return "pointing"
        if index and middle and not ring and not pinky and not thumb:
            return "victory"
        if (
            thumb
            and not index
            and not middle
            and not ring
            and not pinky
            and thumb_ratio >= 1.55
            and index_ratio < 1.05
            and middle_ratio < 1.05
            and ring_ratio < 1.05
            and pinky_ratio < 1.05
        ):
            return "thumbs_up"
        if (
            thumb
            and index
            and not middle
            and not ring
            and not pinky
            and thumb_ratio >= 1.45
            and index_ratio >= 1.45
            and abs(
                float(finger_states["thumb"]["normalized_root_tip_distance"])
                - float(finger_states["index"]["normalized_root_tip_distance"])
            )
            <= 0.35
        ):
            return "pinching"
        if thumb and index and middle and not ring and not pinky:
            return "three_finger"
        if thumb and index and middle and ring and not pinky:
            return "four_finger"
        if index and middle and ring and pinky and not thumb:
            return "spread_hand"
        if thumb and pinky and not index and not middle and not ring and pinky_ratio >= 1.7:
            return "call_me"
        if curled_count >= 4 and extended_count <= 1:
            return "holding"
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
