#!/usr/bin/env python3
"""专家系统本地测试与PC-Pi闭环仿真。"""

import argparse
import base64
import json
import time

from pcside.core.expert_closed_loop import (
    ExpertResult,
    build_expert_result_command,
    parse_pi_expert_ack,
    parse_pi_expert_packet,
)
from pcside.core.expert_manager import ExpertManager


def _fake_frame():
    try:
        import cv2  # type: ignore
        import numpy as np  # type: ignore

        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        cv2.rectangle(frame, (70, 120), (250, 170), (255, 255, 255), -1)
        cv2.circle(frame, (160, 115), 40, (220, 220, 220), -1)
        return frame
    except Exception:
        return None


def run_local(manager: ExpertManager):
    frame = _fake_frame()
    cases = [
        ("危化品识别", {"detected_classes": "person,bottle,glove"}),
        ("仪器操作巡检", {"detected_classes": "person,pipette,phone"}),
        ("PPE穿戴检查", {"detected_classes": "person"}),
        ("实验室智能问答", {"query": "HF操作需要哪些防护？"}),
        ("接触角检测", {"detected_classes": "droplet"}),
        ("微纳流体多模型巡检", {"detected_classes": "droplet,chip"}),
        ("综合安全巡检", {"detected_classes": "person,bottle,phone"}),
        ("明火烟雾巡检", {"detected_classes": "burner"}),
        ("液体洒漏巡检", {"detected_classes": "lab bench"}),
    ]
    for event, ctx in cases:
        res = manager.route_and_analyze(event, frame, ctx)
        print(f"[{event}] => {res}")


def run_joint_sim(manager: ExpertManager):
    frame = _fake_frame()
    if frame is None:
        print("joint 模式跳过：缺少 cv2/numpy 运行时依赖")
        return

    import cv2  # type: ignore

    ok, buf = cv2.imencode(".jpg", frame)
    assert ok
    payload = {
        "event_id": "demo-e2e-1",
        "event_name": "PPE穿戴检查",
        "detected_classes": "person",
        "timestamp": time.time(),
    }
    packet = f"PI_EXPERT_EVENT:{json.dumps(payload, ensure_ascii=False)}:{base64.b64encode(buf.tobytes()).decode('utf-8')}"

    event, err = parse_pi_expert_packet(packet)
    if err or event is None:
        raise RuntimeError(f"parse event failed: {err}")

    text = manager.route_and_analyze(event.event_name, event.frame, {"detected_classes": event.detected_classes})
    result_cmd = build_expert_result_command(ExpertResult(event_id=event.event_id, text=text, speak=False))
    print("CMD =>", result_cmd)

    ack_raw = f"PI_EXPERT_ACK:{json.dumps({'event_id': event.event_id, 'received': True}, ensure_ascii=False)}"
    ack, ack_err = parse_pi_expert_ack(ack_raw)
    if ack_err or not ack:
        raise RuntimeError(f"ack parse failed: {ack_err}")
    print("ACK =>", ack)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["local", "joint", "all"], default="all")
    args = parser.parse_args()

    manager = ExpertManager()
    print(json.dumps(manager.run_self_checks(), ensure_ascii=False, indent=2))

    if args.mode in ["local", "all"]:
        run_local(manager)
    if args.mode in ["joint", "all"]:
        run_joint_sim(manager)


if __name__ == "__main__":
    main()
