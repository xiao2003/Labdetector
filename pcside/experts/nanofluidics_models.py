"""Classic nanofluidics algorithms ported from common MATLAB workflows to Python.

These functions intentionally keep formula style close to MATLAB prototypes
for easier migration of existing lab scripts.
"""

from __future__ import annotations

from typing import Dict, Tuple


def estimate_contact_angle_from_silhouette(frame) -> Tuple[float, bool]:
    try:
        import cv2  # type: ignore
    except Exception:
        return 0.0, False

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blur, 50, 130)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return 0.0, False
    c = max(contours, key=cv2.contourArea)
    if cv2.contourArea(c) < 100:
        return 0.0, False
    _, _, w, h = cv2.boundingRect(c)
    ratio = h / max(1.0, float(w))
    angle = max(5.0, min(175.0, 15.0 + 230.0 * ratio))
    return angle, True


def estimate_particle_velocity_lk(prev_frame, curr_frame) -> Tuple[float, bool]:
    """Lucas-Kanade optical-flow mean velocity (MATLAB: opticalFlowLK analogue)."""
    try:
        import cv2  # type: ignore
        import numpy as np  # type: ignore
    except Exception:
        return 0.0, False

    prev = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)
    curr = cv2.cvtColor(curr_frame, cv2.COLOR_BGR2GRAY)
    p0 = cv2.goodFeaturesToTrack(prev, maxCorners=120, qualityLevel=0.03, minDistance=7)
    if p0 is None:
        return 0.0, False
    p1, st, _ = cv2.calcOpticalFlowPyrLK(prev, curr, p0, None)
    if p1 is None or st is None:
        return 0.0, False

    good_new = p1[st == 1]
    good_old = p0[st == 1]
    if len(good_new) == 0:
        return 0.0, False

    d = good_new - good_old
    speed = float(np.mean(np.sqrt((d[:, 0] ** 2) + (d[:, 1] ** 2))))
    return speed, True


def estimate_meniscus_curvature(frame) -> Tuple[float, bool]:
    """Simple curvature proxy for meniscus shape stability."""
    try:
        import cv2  # type: ignore
        import numpy as np  # type: ignore
    except Exception:
        return 0.0, False

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    edges = cv2.Canny(gray, 70, 140)
    ys, xs = np.where(edges > 0)
    if len(xs) < 20:
        return 0.0, False
    coeff = np.polyfit(xs.astype(float), ys.astype(float), deg=2)  # y = ax^2 + bx + c
    curvature = float(abs(2.0 * coeff[0]))
    return curvature, True


def run_nanofluidics_suite(frame, prev_frame=None) -> Dict[str, float]:
    out: Dict[str, float] = {}
    angle, ok = estimate_contact_angle_from_silhouette(frame)
    if ok:
        out["contact_angle_deg"] = angle
    curv, ok = estimate_meniscus_curvature(frame)
    if ok:
        out["meniscus_curvature"] = curv
    if prev_frame is not None:
        vel, ok = estimate_particle_velocity_lk(prev_frame, frame)
        if ok:
            out["particle_velocity_px_per_frame"] = vel
    return out
