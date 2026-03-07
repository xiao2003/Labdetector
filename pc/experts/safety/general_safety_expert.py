from typing import Dict, List

from pc.core.base_expert import BaseExpert
from pc.experts.utils import has_any, has_all, parse_detected_classes


class GeneralSafetyExpert(BaseExpert):
    @property
    def expert_name(self) -> str:
        return "通用安全行为专家"

    @property
    def expert_version(self) -> str:
        return "2.5"

    def supported_events(self) -> List[str]:
        return ["安防违规-使用手机", "一般安全巡检"]

    def get_edge_policy(self) -> List[Dict]:
        return [
            {
                "event_name": "安防违规-使用手机",
                "trigger_classes": ["person", "cell phone"],
                "condition": "all",
                "action": "full_frame",
                "cooldown": 10.0,
            },
            {
                "event_name": "一般安全巡检",
                "trigger_classes": ["person", "smoke", "fire", "flame"],
                "condition": "any",
                "action": "full_frame",
                "cooldown": 4.0,
            },
        ]

    def match_event(self, event_name: str) -> bool:
        return event_name in self.supported_events()

    def analyze(self, frame, context) -> str:
        detected = parse_detected_classes(context.get("detected_classes", ""))
        if has_all(detected, ["person", "cell", "phone"]) or has_all(detected, ["person", "cell phone"]):
            return "警告：实验操作期间检测到手机使用，请立即停止。"
        if has_any(detected, ["smoke", "fire", "flame"]):
            return "警报：检测到烟雾/火焰迹象，请立即执行应急处置流程。"
        return ""
