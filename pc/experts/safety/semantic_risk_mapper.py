from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional


LAB_INSTRUMENT_ALIASES = {
    "beaker": "烧杯",
    "graduated cylinder": "量筒",
    "test tube": "试管",
    "flask": "烧瓶",
    "erlenmeyer flask": "锥形瓶",
    "pipette": "移液器",
    "micropipette": "微量移液器",
    "dropper": "滴管",
    "bottle": "试剂瓶",
    "reagent bottle": "试剂瓶",
    "petri dish": "培养皿",
    "centrifuge tube": "离心管",
    "vial": "样品瓶",
    "tweezers": "镊子",
    "forceps": "镊子",
    "spatula": "药匙",
    "burner": "酒精灯",
    "hot plate": "加热板",
    "funnel": "漏斗",
    "glass rod": "玻璃棒",
}

HAND_ACTION_TEMPLATES = {
    "holding": "操作人员正在握持{object_name}",
    "pinching": "操作人员正在捏持{object_name}",
    "pointing": "操作人员正在指向{object_name}",
    "open": "操作人员的手部在{object_name}附近展开",
    "partial_open": "操作人员正在接近{object_name}",
}


@dataclass
class SemanticRiskResult:
    risk_level: str
    score: int
    semantics: Dict[str, object]
    reasons: List[str]


def build_semantic_observation(
    event_name: str,
    detected_classes: List[str] | str,
    metrics: Dict[str, float] | None = None,
    context: Dict[str, Any] | None = None,
) -> Dict[str, object]:
    m = metrics or {}
    ctx = context or {}
    classes = {c.lower() for c in _normalize_detected_classes(detected_classes)}
    objects = _extract_objects(ctx)
    hands = _extract_hands(ctx)
    interactions = _infer_hand_object_interactions(hands, objects)
    action_phrases = _build_action_phrases(interactions)
    scene_description = _build_scene_description(classes, objects, hands, action_phrases)

    return {
        "event_name": event_name,
        "has_person": "person" in classes,
        "has_open_flame": any(x in classes for x in ["flame", "fire", "burner"]),
        "has_chemical_container": any(x in classes for x in ["bottle", "reagent bottle", "beaker"]),
        "has_ppe_gloves": any(x in classes for x in ["glove", "gloves"]),
        "has_ppe_eye": any(x in classes for x in ["goggles", "safety glasses", "face shield"]),
        "contact_angle_deg": m.get("contact_angle_deg"),
        "bubble_speed": m.get("bubble_speed"),
        "detected_objects": objects,
        "hand_states": hands,
        "hand_object_interactions": interactions,
        "action_phrases": action_phrases,
        "scene_description": scene_description,
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

    interactions = semantics.get("hand_object_interactions", [])
    if isinstance(interactions, list):
        for item in interactions:
            if not isinstance(item, dict):
                continue
            action = str(item.get("action", "")).lower()
            label = str(item.get("object_label", "")).lower()
            if action == "holding" and label in {"beaker", "bottle", "reagent bottle", "flask"}:
                score += 10
                reasons.append(f"检测到直接握持{_localize_label(label)}")
            if action == "holding" and semantics.get("has_open_flame") and label in {"beaker", "flask", "bottle"}:
                score += 15
                reasons.append(f"存在明火时正在直接握持{_localize_label(label)}")

    if score >= 60:
        level = "high"
    elif score >= 30:
        level = "medium"
    else:
        level = "low"

    return SemanticRiskResult(risk_level=level, score=score, semantics=semantics, reasons=reasons)


def _normalize_detected_classes(raw: List[str] | str | Iterable[str]) -> List[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        return [part.strip() for part in raw.replace(";", ",").split(",") if part.strip()]
    return [str(item).strip() for item in raw if str(item).strip()]


def _extract_objects(context: Dict[str, Any]) -> List[Dict[str, Any]]:
    detections = (
        context.get("detected_boxes")
        or context.get("detections")
        or context.get("objects")
        or context.get("object_detections")
        or []
    )
    objects: List[Dict[str, Any]] = []
    for index, item in enumerate(_force_list(detections)):
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or item.get("class") or item.get("name") or "").strip().lower()
        bbox = _normalize_bbox(item.get("bbox") or item.get("box") or item.get("xyxy") or item.get("rect"))
        if not label or not bbox:
            continue
        objects.append(
            {
                "id": item.get("id", f"obj_{index}"),
                "label": label,
                "name_zh": _localize_label(label),
                "bbox": bbox,
                "score": item.get("score") or item.get("confidence"),
                "is_lab_instrument": label in LAB_INSTRUMENT_ALIASES,
            }
        )
    return objects


def _extract_hands(context: Dict[str, Any]) -> List[Dict[str, Any]]:
    hand_payload = context.get("hand_pose") or context.get("hand_poses") or context.get("hands")
    if not hand_payload and "hand_status" in context:
        hand_payload = {
            "hand_status": context.get("hand_status"),
            "keypoints": context.get("keypoints", []),
            "hands": context.get("hands", []),
        }

    parsed = _maybe_parse_json(hand_payload)
    hands_raw = []
    if isinstance(parsed, dict):
        if isinstance(parsed.get("hands"), list):
            hands_raw = parsed["hands"]
        elif parsed.get("hand_status"):
            hands_raw = [parsed]
    elif isinstance(parsed, list):
        hands_raw = parsed

    hands: List[Dict[str, Any]] = []
    for index, item in enumerate(hands_raw):
        if not isinstance(item, dict):
            continue
        keypoints = item.get("keypoints", [])
        hand_bbox = _bbox_from_keypoints(keypoints)
        hand_center = _bbox_center(hand_bbox) if hand_bbox else _keypoint_center(keypoints)
        if not hand_center:
            continue
        hands.append(
            {
                "id": item.get("id", f"hand_{index}"),
                "hand_status": str(item.get("hand_status", "")).strip().lower(),
                "handedness": str(item.get("handedness", "unknown")).strip().lower(),
                "keypoints": keypoints if isinstance(keypoints, list) else [],
                "bbox": hand_bbox,
                "center": hand_center,
                "extended_fingers": item.get("extended_fingers"),
                "curled_fingers": item.get("curled_fingers"),
            }
        )
    return hands


def _infer_hand_object_interactions(hands: List[Dict[str, Any]], objects: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    interactions: List[Dict[str, Any]] = []
    for hand in hands:
        hand_status = str(hand.get("hand_status", "")).lower()
        if hand_status not in HAND_ACTION_TEMPLATES:
            continue

        best_match: Optional[Dict[str, Any]] = None
        best_score = -1.0
        for obj in objects:
            if not obj.get("is_lab_instrument"):
                continue
            proximity = _compute_hand_object_proximity(hand, obj)
            if not proximity["is_close"]:
                continue
            relation_score = float(proximity["iou"]) * 2.0 + (1.0 - float(proximity["normalized_distance"]))
            if relation_score > best_score:
                best_score = relation_score
                best_match = {
                    "hand_id": hand.get("id"),
                    "handedness": hand.get("handedness"),
                    "action": hand_status,
                    "object_id": obj.get("id"),
                    "object_label": obj.get("label"),
                    "object_name": obj.get("name_zh"),
                    "iou": round(float(proximity["iou"]), 4),
                    "normalized_distance": round(float(proximity["normalized_distance"]), 4),
                    "relation": "overlap" if float(proximity["iou"]) > 0 else "near",
                    "sentence": HAND_ACTION_TEMPLATES[hand_status].format(object_name=obj.get("name_zh")),
                }
        if best_match:
            interactions.append(best_match)
    return interactions


def _build_action_phrases(interactions: List[Dict[str, Any]]) -> List[str]:
    phrases = []
    for item in interactions:
        sentence = str(item.get("sentence", "")).strip()
        if sentence:
            phrases.append(sentence)
    return phrases


def _build_scene_description(
    classes: set[str],
    objects: List[Dict[str, Any]],
    hands: List[Dict[str, Any]],
    action_phrases: List[str],
) -> str:
    object_names = sorted({str(item.get("name_zh")) for item in objects if item.get("is_lab_instrument")})
    hand_states = [str(item.get("hand_status")) for item in hands if item.get("hand_status")]

    parts: List[str] = []
    if "person" in classes:
        parts.append("画面中存在操作人员")
    if object_names:
        parts.append("检测到的实验器具包括" + "、".join(object_names))
    if hand_states:
        parts.append("手部姿态状态包括" + "、".join(hand_states))
    if action_phrases:
        parts.extend(action_phrases)
    return "；".join(parts)


def _compute_hand_object_proximity(hand: Dict[str, Any], obj: Dict[str, Any]) -> Dict[str, float | bool]:
    hand_bbox = hand.get("bbox")
    object_bbox = obj.get("bbox")
    hand_center = hand.get("center")
    object_center = _bbox_center(object_bbox)
    iou = _bbox_iou(hand_bbox, object_bbox) if hand_bbox and object_bbox else 0.0

    normalized_distance = 1.0
    if hand_center and object_center and object_bbox:
        dist = math.dist(hand_center, object_center)
        object_scale = max(_bbox_diagonal(object_bbox), 1e-6)
        normalized_distance = dist / object_scale

    is_close = iou >= 0.02 or normalized_distance <= 0.75
    return {"iou": iou, "normalized_distance": normalized_distance, "is_close": is_close}


def _bbox_iou(bbox_a: List[float] | None, bbox_b: List[float] | None) -> float:
    if not bbox_a or not bbox_b:
        return 0.0
    ax1, ay1, ax2, ay2 = bbox_a
    bx1, by1, bx2, by2 = bbox_b
    inter_x1 = max(ax1, bx1)
    inter_y1 = max(ay1, by1)
    inter_x2 = min(ax2, bx2)
    inter_y2 = min(ay2, by2)
    inter_w = max(0.0, inter_x2 - inter_x1)
    inter_h = max(0.0, inter_y2 - inter_y1)
    inter_area = inter_w * inter_h
    if inter_area <= 0:
        return 0.0
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter_area
    return inter_area / union if union > 0 else 0.0


def _bbox_center(bbox: List[float] | None) -> Optional[List[float]]:
    if not bbox:
        return None
    x1, y1, x2, y2 = bbox
    return [(x1 + x2) / 2.0, (y1 + y2) / 2.0]


def _bbox_diagonal(bbox: List[float]) -> float:
    x1, y1, x2, y2 = bbox
    return math.sqrt(max(0.0, x2 - x1) ** 2 + max(0.0, y2 - y1) ** 2)


def _bbox_from_keypoints(keypoints: Any) -> Optional[List[float]]:
    if not isinstance(keypoints, list) or not keypoints:
        return None
    xs = []
    ys = []
    for point in keypoints:
        if not isinstance(point, dict):
            continue
        px = point.get("pixel_x")
        py = point.get("pixel_y")
        if px is not None and py is not None:
            xs.append(float(px))
            ys.append(float(py))
    if not xs or not ys:
        return None
    return [min(xs), min(ys), max(xs), max(ys)]


def _keypoint_center(keypoints: Any) -> Optional[List[float]]:
    if not isinstance(keypoints, list) or not keypoints:
        return None
    xs = []
    ys = []
    for point in keypoints:
        if not isinstance(point, dict):
            continue
        if point.get("pixel_x") is not None and point.get("pixel_y") is not None:
            xs.append(float(point["pixel_x"]))
            ys.append(float(point["pixel_y"]))
        elif point.get("x") is not None and point.get("y") is not None:
            xs.append(float(point["x"]))
            ys.append(float(point["y"]))
    if not xs or not ys:
        return None
    return [sum(xs) / len(xs), sum(ys) / len(ys)]


def _normalize_bbox(raw_bbox: Any) -> Optional[List[float]]:
    if raw_bbox is None:
        return None
    if isinstance(raw_bbox, dict):
        if all(key in raw_bbox for key in ("x1", "y1", "x2", "y2")):
            return [float(raw_bbox["x1"]), float(raw_bbox["y1"]), float(raw_bbox["x2"]), float(raw_bbox["y2"])]
        if all(key in raw_bbox for key in ("x", "y", "w", "h")):
            x = float(raw_bbox["x"])
            y = float(raw_bbox["y"])
            w = float(raw_bbox["w"])
            h = float(raw_bbox["h"])
            return [x, y, x + w, y + h]
        return None
    if isinstance(raw_bbox, (list, tuple)) and len(raw_bbox) == 4:
        x1, y1, x2, y2 = [float(v) for v in raw_bbox]
        if x2 >= x1 and y2 >= y1:
            return [x1, y1, x2, y2]
        return [x1, y1, x1 + x2, y1 + y2]
    return None


def _maybe_parse_json(payload: Any) -> Any:
    if isinstance(payload, str):
        text = payload.strip()
        if not text:
            return None
        try:
            return json.loads(text)
        except Exception:
            return None
    return payload


def _localize_label(label: str) -> str:
    return LAB_INSTRUMENT_ALIASES.get(label.lower(), label)


def _force_list(payload: Any) -> List[Any]:
    if payload is None:
        return []
    if isinstance(payload, list):
        return payload
    return [payload]
