from typing import Dict, List

from pc.core.base_expert import BaseExpert
from pc.experts.utils import has_any, parse_detected_classes


class PPEExpert(BaseExpert):
    """实验室装备穿戴规范专家。"""

    @property
    def expert_name(self):
        return "实验室装备穿戴规范专家"

    @property
    def expert_version(self) -> str:
        return "2.5"

    def supported_events(self) -> List[str]:
        return ["PPE穿戴检查", "危化品识别", "仪器操作巡检"]

    def get_edge_policy(self) -> List[Dict]:
        return [
            {
                "event_name": "PPE穿戴检查",
                "trigger_classes": ["person"],
                "condition": "any",
                "action": "full_frame",
                "cooldown": 8.0,
            },
            {
                "event_name": "危化品识别",
                "trigger_classes": ["person", "bottle"],
                "condition": "all",
                "action": "full_frame",
                "cooldown": 5.0,
            },
        ]

    def match_event(self, event_name):
        return event_name in self.supported_events()

    def analyze(self, frame, context):
        detected = parse_detected_classes(context.get("detected_classes", ""))
        if "person" not in detected:
            return ""

        missing = []
        if not has_any(detected, ["lab coat", "coat", "apron"]):
            missing.append("实验服")
        if not has_any(detected, ["glove", "gloves"]):
            missing.append("手套")
        if not has_any(detected, ["goggles", "safety glasses", "face shield"]):
            missing.append("护目镜")

        if missing:
            return f"PPE 规范提醒：检测到人员但未完整佩戴 {','.join(missing)}。"
        return ""
