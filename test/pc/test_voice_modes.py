#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Focused voice-feature validation for QA, note capture, and voice expert routing."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pc.voice.voice_interaction as voice_module
from pc.core.expert_manager import expert_manager
from pc.knowledge_base.rag_engine import knowledge_manager
from pc.voice.voice_interaction import VoiceInteraction, VoiceInteractionConfig


def _synthetic_hazard_frame() -> np.ndarray:
    frame = np.full((480, 640, 3), 245, dtype=np.uint8)
    cv2.rectangle(frame, (90, 120), (260, 360), (230, 230, 230), -1)
    cv2.rectangle(frame, (120, 150), (230, 330), (220, 220, 255), -1)
    pts = np.array([[175, 180], [135, 255], [215, 255]], dtype=np.int32)
    cv2.fillPoly(frame, [pts], (0, 180, 255))
    cv2.putText(frame, "CHEM", (120, 380), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (40, 40, 40), 2, cv2.LINE_AA)
    return frame


def _run() -> dict:
    report: dict = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "readme_voice_expectations": [
            "语音问答",
            "语音记录并回灌知识库",
            "语音唤醒专家并播报结果",
        ],
        "results": [],
        "tts_messages": [],
    }

    tts_messages: list[str] = []

    def fake_speak(text: str) -> None:
        tts_messages.append(str(text))

    def fake_stop() -> None:
        tts_messages.append("[STOP_TTS]")

    original_speak = voice_module.speak_async
    original_stop = voice_module.stop_tts
    voice_module.speak_async = fake_speak
    voice_module.stop_tts = fake_stop

    try:
        config = VoiceInteractionConfig()
        config.asr_engine = "auto"
        interaction = VoiceInteraction(config)
        interaction.set_ai_backend("ollama", model="gemma3:4b")
        interaction.get_latest_frame_callback = _synthetic_hazard_frame
        interaction.open_runtime_session(
            mode="camera",
            source="pc_local",
            metadata={"project_name": "自动语音测试", "experiment_name": "虚拟语音三场景"},
        )

        note_probe = f"自动测试语音记录 {int(time.time())}"

        scenarios = [
            {
                "name": "qa",
                "command": "介绍当前系统状态",
                "purpose": "验证实验问答和语音播报",
            },
            {
                "name": "note",
                "command": f"帮我记录 {note_probe}",
                "purpose": "验证口头记录自动写入 common 知识库",
            },
            {
                "name": "voice_expert",
                "command": "请识别一下这个化学品标签",
                "purpose": "验证语音命中专家模型并返回结果",
            },
        ]

        for scenario in scenarios:
            before_tts = len(tts_messages)
            response = interaction.process_text_command(
                scenario["command"],
                source="pc_local",
                speak_response=True,
                metadata={"scenario": scenario["name"]},
            )
            entry = {
                "scenario": scenario["name"],
                "purpose": scenario["purpose"],
                "command": scenario["command"],
                "response": response,
                "tts_delta": tts_messages[before_tts:],
            }
            if scenario["name"] == "qa":
                entry["pass"] = bool(response and len(entry["tts_delta"]) >= 1)
            elif scenario["name"] == "note":
                try:
                    common_scope = knowledge_manager.get_scope("common")
                    notes = common_scope.search(note_probe, top_k=5)
                    found = any(note_probe in str(item.get("text", "")) for item in notes)
                except Exception:
                    found = False
                entry["knowledge_saved"] = found
                entry["pass"] = bool(found and "知识库" in response)
            elif scenario["name"] == "voice_expert":
                bundle = expert_manager.route_voice_command(
                    scenario["command"],
                    _synthetic_hazard_frame(),
                    {"source": "pc_local", "query": scenario["command"], "question": scenario["command"]},
                )
                matched = bundle.get("matched_expert_codes", [])
                entry["matched_expert_codes"] = matched
                entry["pass"] = bool(matched and "safety.chem_safety_expert" in matched and response)
            report["results"].append(entry)

        report["tts_messages"] = tts_messages
        report["pass_count"] = sum(1 for item in report["results"] if item.get("pass"))
        report["fail_count"] = sum(1 for item in report["results"] if not item.get("pass"))
        return report
    finally:
        voice_module.speak_async = original_speak
        voice_module.stop_tts = original_stop


def main() -> int:
    report = _run()
    output = Path(__file__).resolve().parent / "voice_modes_report.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(output))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
