from __future__ import annotations

import json
from pathlib import Path
import sys

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pc.core.expert_manager import expert_manager


def make_text_frame(lines: list[str]) -> np.ndarray:
    frame = np.full((360, 640, 3), 245, dtype=np.uint8)
    y = 80
    for line in lines:
        cv2.putText(frame, line, (40, y), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (20, 20, 20), 2, cv2.LINE_AA)
        y += 60
    return frame


def main() -> None:
    policies = expert_manager.get_aggregated_edge_policy().get("event_policies", [])
    policy_codes = sorted({str(item.get("expert_code", "") or "") for item in policies})

    chem_frame = make_text_frame(["HF", "Wear gloves", "Bottle A"])
    chem_voice = expert_manager.route_voice_command(
        "小爱同学，请识别一下这个化学品标签",
        chem_frame,
        {"source": "check_closed_loop_focus", "detected_classes": "bottle"},
    )

    ocr_frame = make_text_frame(["TEMP 25.6C", "PRESS 1.2bar", "RPM 1500"])
    ocr_voice = expert_manager.route_voice_command(
        "小爱同学，读一下这个设备屏幕内容",
        ocr_frame,
        {"source": "check_closed_loop_focus"},
    )

    report = {
        "policy_codes": policy_codes,
        "policy_count": len(policies),
        "chem_voice_codes": chem_voice.get("matched_expert_codes") or [],
        "ocr_voice_codes": ocr_voice.get("matched_expert_codes") or [],
        "policy_events": [
            {
                "event_name": item.get("event_name", ""),
                "expert_code": item.get("expert_code", ""),
                "policy_name": item.get("policy_name", ""),
                "policy_action": item.get("policy_action", item.get("action", "")),
            }
            for item in policies
        ],
    }
    output = Path(__file__).with_name("check_closed_loop_focus_report.json")
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
