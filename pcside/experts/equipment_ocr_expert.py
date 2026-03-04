from typing import Dict, List

from pcside.core.base_expert import BaseExpert
from pcside.experts.utils import has_any, parse_detected_classes


class EquipmentOperationExpert(BaseExpert):
    """实验室仪器操作规范专家。"""

    @property
    def expert_name(self):
        return "实验室仪器操作规范专家"

    @property
    def expert_version(self) -> str:
        return "2.5"

    def supported_events(self) -> List[str]:
        return ["仪器操作巡检", "Equipment_Status_Sync"]

    def get_edge_policy(self) -> Dict:
        return {
            "event_name": "仪器操作巡检",
            "trigger_classes": ["microscope", "centrifuge", "pipette", "hot plate", "person"],
            "condition": "any",
            "action": "full_frame",
            "cooldown": 6.0,
        }

    def match_event(self, event_name):
        return event_name in self.supported_events()

    def analyze(self, frame, context):
        detected = parse_detected_classes(context.get("detected_classes", ""))

        if has_any(detected, ["centrifuge", "centrifuge lid open"]):
            if "person" in detected and "glove" not in detected:
                return "离心机操作警告：疑似未佩戴手套，请先完成PPE再操作。"

        if has_any(detected, ["hot plate", "heater", "bunsen burner"]):
            if has_any(detected, ["paper", "book", "phone"]):
                return "热源邻近可燃物，存在起火风险，请立即清理实验台。"

        if has_any(detected, ["pipette", "pipettor", "micro pipette"]) and "person" in detected:
            if has_any(detected, ["phone", "cell", "cellphone"]):
                return "移液操作中检测到手机使用，建议立即停止并避免交叉污染。"

        return ""
