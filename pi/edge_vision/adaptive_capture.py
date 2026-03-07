from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass
class CaptureProfile:
    fps: float
    preview_width: int
    preview_height: int
    preview_jpeg_quality: int
    event_jpeg_quality: int


class AdaptiveCaptureController:
    """边缘视觉采集自适配控制器。

    目标：在光照波动、清晰度变化、运动强度变化下，动态平衡帧率/分辨率/压缩质量/存储成本。
    """

    def __init__(self, min_fps: float = 2.0, max_fps: float = 15.0):
        self.min_fps = min_fps
        self.max_fps = max_fps

    def evaluate_frame(self, frame) -> Dict[str, float]:
        try:
            import cv2  # type: ignore
            import numpy as np  # type: ignore
        except Exception:
            return {"brightness": 128.0, "blur": 0.0, "motion_score": 0.0}

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        brightness = float(gray.mean())
        blur = float(cv2.Laplacian(gray, cv2.CV_64F).var())

        # 简易运动评分：边缘像素占比近似
        edges = cv2.Canny(gray, 70, 140)
        motion_score = float(np.count_nonzero(edges)) / float(edges.size)
        return {"brightness": brightness, "blur": blur, "motion_score": motion_score}

    def suggest_profile(self, metrics: Dict[str, float], storage_budget_mb_per_hour: float = 500.0) -> CaptureProfile:
        brightness = metrics.get("brightness", 128.0)
        blur = metrics.get("blur", 0.0)
        motion = metrics.get("motion_score", 0.0)

        # 光照暗且清晰度低：提升质量与分辨率，避免细节损失
        if brightness < 70 or blur < 40:
            base_w, base_h = 960, 720
            preview_q = 82
        elif motion > 0.10:
            base_w, base_h = 800, 600
            preview_q = 75
        else:
            base_w, base_h = 640, 480
            preview_q = 68

        # 存储预算约束：预算越紧，fps 越低
        if storage_budget_mb_per_hour < 250:
            fps = self.min_fps
        elif storage_budget_mb_per_hour < 500:
            fps = 4.0
        else:
            fps = 6.0

        fps = max(self.min_fps, min(self.max_fps, fps))
        event_q = max(88, preview_q + 12)

        return CaptureProfile(
            fps=fps,
            preview_width=base_w,
            preview_height=base_h,
            preview_jpeg_quality=preview_q,
            event_jpeg_quality=event_q,
        )
