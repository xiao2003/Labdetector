from typing import Dict, List

from pc.core.base_expert import BaseExpert


class SpillDetectionExpert(BaseExpert):
    """中小型实验室常见：液体洒漏检测专家。"""

    @property
    def expert_name(self) -> str:
        return "液体洒漏检测专家"

    @property
    def expert_version(self) -> str:
        return "2.5"

    def supported_events(self) -> List[str]:
        return ["液体洒漏巡检"]

    def get_edge_policy(self) -> Dict:
        return {
            "event_name": "液体洒漏巡检",
            "trigger_classes": ["table", "desk", "lab bench"],
            "condition": "any",
            "action": "full_frame",
            "cooldown": 6.0,
        }

    def match_event(self, event_name: str) -> bool:
        return event_name in self.supported_events()

    def analyze(self, frame, context) -> str:
        if frame is None:
            return ""
        try:
            import cv2  # type: ignore
        except Exception:
            return ""

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (7, 7), 0)
        th = cv2.adaptiveThreshold(blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 21, 4)
        contours, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        large = [c for c in contours if cv2.contourArea(c) > 1200]
        if large:
            return "洒漏风险：实验台出现大面积异常液体形态，请立即清理并检查样品容器。"
        return ""
