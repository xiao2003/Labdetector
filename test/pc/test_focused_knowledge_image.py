from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pc.core.expert_manager import expert_manager
from pc.knowledge_base.rag_engine import knowledge_manager


OUT_DIR = ROOT / "tmp" / "focused_knowledge_assets"
REPORT_PATH = ROOT / "tmp" / "focused_knowledge_image_report.json"


def make_hf_label_frame() -> np.ndarray:
    frame = np.full((540, 960, 3), 248, dtype=np.uint8)
    cv2.rectangle(frame, (110, 70), (850, 470), (40, 60, 80), 4)
    cv2.putText(frame, "Hydrofluoric Acid", (160, 160), cv2.FONT_HERSHEY_SIMPLEX, 1.6, (10, 10, 10), 4, cv2.LINE_AA)
    cv2.putText(frame, "HF", (380, 310), cv2.FONT_HERSHEY_SIMPLEX, 4.2, (0, 0, 0), 10, cv2.LINE_AA)
    cv2.putText(frame, "Wear gloves and face shield", (150, 420), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (15, 15, 15), 3, cv2.LINE_AA)
    return frame


def make_ppe_scene_frame() -> np.ndarray:
    frame = np.full((540, 960, 3), 232, dtype=np.uint8)
    cv2.rectangle(frame, (80, 60), (880, 480), (70, 70, 70), 3)
    cv2.circle(frame, (300, 170), 42, (30, 30, 30), 4)
    cv2.line(frame, (300, 212), (300, 360), (30, 30, 30), 5)
    cv2.line(frame, (300, 245), (220, 315), (30, 30, 30), 5)
    cv2.line(frame, (300, 245), (380, 315), (30, 30, 30), 5)
    cv2.line(frame, (300, 360), (245, 455), (30, 30, 30), 5)
    cv2.line(frame, (300, 360), (355, 455), (30, 30, 30), 5)
    cv2.rectangle(frame, (560, 220), (690, 420), (80, 120, 160), 3)
    cv2.putText(frame, "Bottle", (555, 205), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (20, 20, 20), 2, cv2.LINE_AA)
    cv2.putText(frame, "No goggles / gloves / coat", (170, 505), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (20, 20, 20), 2, cv2.LINE_AA)
    return frame


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    hf_frame = make_hf_label_frame()
    ppe_frame = make_ppe_scene_frame()
    hf_path = OUT_DIR / "hf_label_test.jpg"
    ppe_path = OUT_DIR / "ppe_scene_test.jpg"
    cv2.imwrite(str(hf_path), hf_frame)
    cv2.imwrite(str(ppe_path), ppe_frame)

    chem_scope = "expert.safety.chem_safety_expert"
    ppe_scope = "expert.safety.ppe_expert"

    chem_bundle = knowledge_manager.build_scope_bundle("HF 手套 面屏 通风橱", chem_scope, top_k=3)
    ppe_bundle = knowledge_manager.build_scope_bundle("实验服 手套 护目镜 PPE", ppe_scope, top_k=3)

    chem_voice = expert_manager.route_voice_command(
        "请识别一下这个化学品标签",
        hf_frame,
        {"source": "focused_knowledge_test", "detected_classes": "bottle", "query": "HF 手套 面屏 通风橱"},
    )

    ppe_expert = next(
        (instance for instance in expert_manager.experts.values() if getattr(instance, "expert_code", "") == "safety.ppe_expert"),
        None,
    )
    ppe_result = ""
    if ppe_expert is not None:
        ppe_result = ppe_expert.analyze(
            ppe_frame,
            {"event_name": "PPE穿戴检查", "detected_classes": "person bottle"},
        )

    report = {
        "assets": {
            "hf_label_image": str(hf_path),
            "ppe_scene_image": str(ppe_path),
        },
        "knowledge": {
            "chem_scope": chem_scope,
            "chem_context_nonempty": bool(str(chem_bundle.get("context", "")).strip()),
            "chem_structured_rows": len(chem_bundle.get("structured_rows") or []),
            "chem_vector_hits": len(chem_bundle.get("vector_hits") or []),
            "ppe_scope": ppe_scope,
            "ppe_context_nonempty": bool(str(ppe_bundle.get("context", "")).strip()),
            "ppe_structured_rows": len(ppe_bundle.get("structured_rows") or []),
            "ppe_vector_hits": len(ppe_bundle.get("vector_hits") or []),
        },
        "expert_results": {
            "chem_matched_expert_codes": chem_voice.get("matched_expert_codes") or [],
            "chem_text": chem_voice.get("text") or "",
            "ppe_text": ppe_result,
        },
    }
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(REPORT_PATH)


if __name__ == "__main__":
    main()
