from typing import Dict, List

from pcside.core.base_expert import BaseExpert
from pcside.experts.utils import has_any, parse_detected_classes
from pcside.experts.safety.semantic_risk_mapper import build_semantic_observation, map_semantic_risk


class IntegratedLabSafetyExpert(BaseExpert):
    """聚合式综合安全专家：整合危化/PPE/行为/热源风险。"""

    @property
    def expert_name(self) -> str:
        return "综合实验室安全聚合专家"

    @property
    def expert_version(self) -> str:
        return "2.6"

    def supported_events(self) -> List[str]:
        return ["综合安全巡检"]

    def get_edge_policy(self) -> Dict:
        return {
            "event_name": "综合安全巡检",
            "trigger_classes": ["person", "bottle", "cell phone", "hot plate", "burner"],
            "condition": "any",
            "action": "full_frame",
            "cooldown": 3.0,
        }

    def match_event(self, event_name: str) -> bool:
        return event_name in self.supported_events()

    def analyze(self, frame, context) -> str:
        d = parse_detected_classes(context.get("detected_classes", ""))
        alerts = []

        if "person" in d:
            if not has_any(d, ["lab coat", "coat", "apron"]):
                alerts.append("实验服缺失")
            if not has_any(d, ["glove", "gloves"]):
                alerts.append("手套缺失")
            if not has_any(d, ["goggles", "safety glasses", "face shield"]):
                alerts.append("护目镜缺失")

        if "person" in d and has_any(d, ["cell", "phone", "cell phone"]):
            alerts.append("操作时使用手机")

        if has_any(d, ["hot plate", "burner", "flame", "fire"]) and has_any(d, ["paper", "book"]):
            alerts.append("热源邻近可燃物")

        if has_any(d, ["bottle", "reagent bottle"]) and not has_any(d, ["glove", "gloves"]):
            alerts.append("试剂操作未佩戴手套")

        sem = build_semantic_observation(
            event_name=str(context.get("event_name", "")),
            detected_classes=d,
            metrics=context.get("metrics", {}),
            context=context,
        )
        risk = map_semantic_risk(sem)

        if alerts:
            return "综合风险告警：" + "；".join(alerts) + f"。语义风险等级={risk.risk_level}({risk.score})"

        if risk.risk_level in ["medium", "high"] and risk.reasons:
            return f"语义风险提示：等级={risk.risk_level}({risk.score})；" + "；".join(risk.reasons)
        return ""
