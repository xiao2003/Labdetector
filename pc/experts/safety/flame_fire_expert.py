from typing import Dict, List

from pc.core.base_expert import BaseExpert


class FlameFireExpert(BaseExpert):
    """中小型实验室常见：明火/烟雾风险检测专家。"""

    @property
    def expert_name(self) -> str:
        return "火焰烟雾风险专家"

    @property
    def expert_version(self) -> str:
        return "2.5"

    def supported_events(self) -> List[str]:
        return ["明火烟雾巡检", "一般安全巡检"]

    def get_edge_policy(self) -> Dict:
        return {
            "event_name": "明火烟雾巡检",
            "trigger_classes": ["fire", "flame", "smoke", "burner"],
            "condition": "any",
            "action": "full_frame",
            "cooldown": 3.0,
        }

    def match_event(self, event_name: str) -> bool:
        return event_name in self.supported_events()

    def analyze(self, frame, context) -> str:
        if frame is None:
            return ""
        try:
            import cv2  # type: ignore
            import numpy as np  # type: ignore
        except Exception:
            return ""

        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        # 火焰颜色阈值（橙黄）
        mask = cv2.inRange(hsv, (5, 120, 120), (35, 255, 255))
        flame_ratio = float(np.count_nonzero(mask)) / float(mask.size)
        if flame_ratio > 0.05:
            return "火焰风险：画面检测到明显火焰区域，请核对防火措施。"
        return ""
