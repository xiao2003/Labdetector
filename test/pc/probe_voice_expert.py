# -*- coding: utf-8 -*-
from __future__ import annotations

import sys

import cv2
import numpy as np

ROOT = r"D:\Labdetector-master\Labdetector-master"
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from pc.core.expert_manager import expert_manager


def main() -> None:
    command = "请识别一下这个化学品标签"
    frame = np.full((520, 720, 3), 255, dtype=np.uint8)
    cv2.putText(frame, "HF", (230, 260), cv2.FONT_HERSHEY_SIMPLEX, 5.0, (0, 0, 0), 12, cv2.LINE_AA)
    context = {"source": "pc_local", "query": command, "question": command, "detected_classes": ["bottle"]}
    print("bundle=", expert_manager.route_voice_command(command, frame, context))


if __name__ == "__main__":
    main()
