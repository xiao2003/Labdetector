#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Live hand pose test window for manual validation."""

from __future__ import annotations

import argparse
from collections import deque
import json
import sys
import time
import tkinter as tk
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import cv2
from PIL import Image, ImageTk

from pc.core.logger import console_error, console_info
from pc.experts.safety.hand_pose_expert import HandPoseExpert


def _draw_overlay(frame, lines, color=(0, 255, 0)):
    y = 30
    for line in lines:
        cv2.putText(frame, line, (16, y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 4, cv2.LINE_AA)
        cv2.putText(frame, line, (16, y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2, cv2.LINE_AA)
        y += 28


def _build_hand_lines(result: dict) -> list[str]:
    hands = result.get("hands") or []
    lines = []
    for idx, hand in enumerate(hands[:2], start=1):
        handedness = str(hand.get("handedness", "unknown"))
        status = str(hand.get("hand_status", "unknown"))
        extended = hand.get("extended_fingers", "-")
        curled = hand.get("curled_fingers", "-")
        finger_states = hand.get("finger_states") or {}
        flags = []
        for finger_name, short in (("thumb", "T"), ("index", "I"), ("middle", "M"), ("ring", "R"), ("pinky", "P")):
            state = finger_states.get(finger_name) or {}
            flags.append(f"{short}:{'1' if state.get('extended') else '0'}")
        lines.append(f"hand{idx}: {handedness} {status}  ext={extended} cur={curled}")
        lines.append("      " + " ".join(flags))
    return lines


def _stable_value(history: deque[str], fallback: str) -> str:
    if not history:
        return fallback
    counts: dict[str, int] = {}
    for item in history:
        counts[item] = counts.get(item, 0) + 1
    return max(counts.items(), key=lambda item: item[1])[0]


def _open_camera(camera_index: int):
    candidates = [
        ("default", lambda: cv2.VideoCapture(camera_index)),
        ("dshow", lambda: cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)),
        ("msmf", lambda: cv2.VideoCapture(camera_index, cv2.CAP_MSMF)),
    ]
    for backend_name, factory in candidates:
        capture = factory()
        if capture is not None and capture.isOpened():
            console_info(f"手部姿态测试已使用摄像头后端: {backend_name} (index={camera_index})")
            return capture
        if capture is not None:
            capture.release()
    return None


def run(camera_index: int = 0) -> int:
    expert = HandPoseExpert()
    capture = _open_camera(camera_index)
    if capture is None or not capture.isOpened():
        console_error(f"手部姿态测试无法打开摄像头: index={camera_index}")
        return 1

    capture.set(cv2.CAP_PROP_FRAME_WIDTH, 960)
    capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 540)
    capture.set(cv2.CAP_PROP_FPS, 15)

    console_info("手部姿态实时测试已启动。按 Q 退出，按 S 打印当前识别结果。")

    root = tk.Tk()
    root.title("NeuroLab Hub - Hand Pose Live Test")
    root.configure(bg="#15202b")
    image_label = tk.Label(root, bg="#15202b")
    image_label.pack(padx=12, pady=12)
    status_var = tk.StringVar(value="准备中...")
    status_label = tk.Label(root, textvariable=status_var, fg="#d8f3ff", bg="#15202b", font=("Microsoft YaHei", 11))
    status_label.pack(padx=12, pady=(0, 12), anchor="w")

    last_result = {"hand_status": "waiting", "hands": []}
    running = {"value": True}
    status_history: deque[str] = deque(maxlen=5)
    hand_history: dict[int, deque[str]] = {0: deque(maxlen=5), 1: deque(maxlen=5)}
    displayed_status = "waiting"
    displayed_hands: list[dict] = []
    last_switch_ts = 0.0

    def _print_result(_event=None):
        console_info("当前手部姿态结果: " + json.dumps(last_result, ensure_ascii=False))

    def _close(_event=None):
        running["value"] = False
        try:
            root.destroy()
        except Exception:
            pass

    root.bind("<KeyPress-q>", _close)
    root.bind("<KeyPress-Q>", _close)
    root.bind("<Escape>", _close)
    root.bind("<KeyPress-s>", _print_result)
    root.bind("<KeyPress-S>", _print_result)

    try:
        while running["value"]:
            ok, frame = capture.read()
            if not ok or frame is None:
                console_error("手部姿态测试读取摄像头失败")
                time.sleep(0.1)
                try:
                    root.update_idletasks()
                    root.update()
                except tk.TclError:
                    break
                continue

            try:
                raw = expert.analyze(frame, {"event_name": "hand_pose_analysis"})
                parsed = json.loads(raw)
                last_result = parsed if isinstance(parsed, dict) else {"hand_status": "unknown", "raw": raw}
            except Exception as exc:
                last_result = {"hand_status": "error", "reason": str(exc)}

            hand_status = str(last_result.get("hand_status", "unknown"))
            hands = last_result.get("hands") or []
            status_history.append(hand_status)
            for idx in range(2):
                current_status = str(hands[idx].get("hand_status", "missing")) if idx < len(hands) else "missing"
                hand_history[idx].append(current_status)

            candidate_status = _stable_value(status_history, hand_status)
            candidate_hands: list[dict] = []
            for idx in range(min(2, len(hands))):
                row = dict(hands[idx])
                row["hand_status"] = _stable_value(hand_history[idx], str(row.get("hand_status", "unknown")))
                candidate_hands.append(row)

            now = time.time()
            if candidate_status != displayed_status:
                if now - last_switch_ts >= 0.45:
                    displayed_status = candidate_status
                    displayed_hands = candidate_hands
                    last_switch_ts = now
            else:
                displayed_hands = candidate_hands

            summary = last_result.get("summary") or {}
            if displayed_hands:
                primary = displayed_hands[0]
                handedness = primary.get("handedness", "unknown")
                extended = primary.get("extended_fingers", "-")
                curled = primary.get("curled_fingers", "-")
            else:
                handedness = summary.get("handedness", "unknown")
                extended = summary.get("extended_fingers", "-")
                curled = summary.get("curled_fingers", "-")

            color = (0, 200, 0)
            if displayed_status in ("error", "dependency_missing", "no_frame"):
                color = (0, 0, 255)
            elif displayed_status in ("no_hand", "partial_open"):
                color = (0, 200, 255)

            stable_result = dict(last_result)
            stable_result["hand_status"] = displayed_status
            stable_result["hands"] = displayed_hands

            lines = [
                "Hand Pose Live Test",
                f"status: {displayed_status}",
                f"hands: {len(hands)}  primary: {handedness}",
                f"extended: {extended}  curled: {curled}",
            ]
            lines.extend(_build_hand_lines(stable_result))
            lines.extend([
                "keys: Q quit / S print result",
            ])
            _draw_overlay(frame, lines, color=color)

            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            image = Image.fromarray(frame_rgb)
            tk_image = ImageTk.PhotoImage(image=image)
            image_label.configure(image=tk_image)
            image_label.image = tk_image
            status_var.set(
                f"status={displayed_status} | hands={len(hands)} | primary={handedness} | extended={extended} | curled={curled}"
            )

            try:
                root.update_idletasks()
                root.update()
            except tk.TclError:
                break
    finally:
        capture.release()
        try:
            root.destroy()
        except Exception:
            pass

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="NeuroLab Hub 手部姿态实时测试")
    parser.add_argument("--camera-index", type=int, default=0, help="摄像头索引，默认 0")
    args = parser.parse_args()
    return run(camera_index=args.camera_index)


if __name__ == "__main__":
    raise SystemExit(main())
