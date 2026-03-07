import math
from typing import Dict, List, Tuple

from pc.core.base_expert import BaseExpert


class MicrofluidicContactAngleExpert(BaseExpert):
    """微纳流体接触角视频识别模型专家（轻量CV版本）。"""

    @property
    def expert_name(self) -> str:
        return "微纳流体接触角分析专家"

    @property
    def expert_version(self) -> str:
        return "2.5"

    def supported_events(self) -> List[str]:
        return ["接触角检测", "microfluidic_contact_angle"]

    def get_edge_policy(self) -> Dict:
        return {
            "event_name": "接触角检测",
            "trigger_classes": ["droplet", "petri dish", "slide"],
            "condition": "any",
            "action": "crop_target",
            "cooldown": 2.0,
        }

    def match_event(self, event_name: str) -> bool:
        return event_name in self.supported_events()

    def _estimate_contact_angle(self, frame) -> Tuple[float, bool]:
        try:
            import cv2  # type: ignore
        except Exception:
            return 0.0, False

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blur, 60, 140)
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return 0.0, False

        c = max(contours, key=cv2.contourArea)
        if cv2.contourArea(c) < 120:
            return 0.0, False

        x, y, w, h = cv2.boundingRect(c)
        if w <= 0 or h <= 0:
            return 0.0, False

        # 用宽高比做近似估计：越扁平接触角越小，越高耸接触角越大。
        ratio = h / float(w)
        angle = max(5.0, min(175.0, 20.0 + 220.0 * ratio))
        return angle, True

    def analyze(self, frame, context) -> str:
        if frame is None:
            return ""
        angle, ok = self._estimate_contact_angle(frame)
        if not ok:
            return "接触角分析：未检测到稳定液滴轮廓。"

        low = float(context.get("angle_low", 60))
        high = float(context.get("angle_high", 110))
        if angle < low or angle > high:
            return f"接触角异常：当前约 {angle:.1f}°，超出建议范围[{low:.0f},{high:.0f}]°。"
        return f"接触角正常：当前约 {angle:.1f}°。"
