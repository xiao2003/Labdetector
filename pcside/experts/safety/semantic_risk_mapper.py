from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


@dataclass
class SemanticRiskResult:
    risk_level: str
    score: int
    semantics: Dict[str, object]
    reasons: List[str]


def build_semantic_observation(event_name: str, detected_classes: List[str], metrics: Dict[str, float] | None = None) -> Dict[str, object]:
    m = metrics or {}
    classes = {c.lower() for c in detected_classes}
    return {
        "event_name": event_name,
        "has_person": "person" in classes,
        "has_open_flame": any(x in classes for x in ["flame", "fire", "burner"]),
        "has_chemical_container": any(x in classes for x in ["bottle", "reagent bottle", "beaker"]),
        "has_ppe_gloves": any(x in classes for x in ["glove", "gloves"]),
        "has_ppe_eye": any(x in classes for x in ["goggles", "safety glasses", "face shield"]),
        "contact_angle_deg": m.get("contact_angle_deg"),
        "bubble_speed": m.get("bubble_speed"),
    }


def map_semantic_risk(semantics: Dict[str, object]) -> SemanticRiskResult:
    score = 0
    reasons: List[str] = []

    if semantics.get("has_open_flame") and semantics.get("has_chemical_container"):
        score += 45
        reasons.append("明火与化学容器同时出现")

    if semantics.get("has_person") and not semantics.get("has_ppe_gloves"):
        score += 20
        reasons.append("人员操作但未检测到手套")

    if semantics.get("has_person") and not semantics.get("has_ppe_eye"):
        score += 15
        reasons.append("人员操作但未检测到眼部防护")

    ca = semantics.get("contact_angle_deg")
    if isinstance(ca, (int, float)) and (ca < 40 or ca > 140):
        score += 10
        reasons.append("接触角异常，可能伴随操作风险")

    bs = semantics.get("bubble_speed")
    if isinstance(bs, (int, float)) and bs > 20:
        score += 10
        reasons.append("气泡运动过快，建议复核驱动条件")

    if score >= 60:
        level = "high"
    elif score >= 30:
        level = "medium"
    else:
        level = "low"

    return SemanticRiskResult(risk_level=level, score=score, semantics=semantics, reasons=reasons)
