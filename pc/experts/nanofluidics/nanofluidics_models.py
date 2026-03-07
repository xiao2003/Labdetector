"""Classic nanofluidics algorithms ported from common MATLAB workflows to Python.

These functions intentionally keep formula style close to MATLAB prototypes
for easier migration of existing lab scripts.
"""

from __future__ import annotations

from typing import Dict, List, Tuple


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


def _extract_bubbles(frame, min_area: float = 120.0) -> List[Dict[str, float]]:
    try:
        import cv2  # type: ignore
        import numpy as np  # type: ignore
    except Exception:
        return []

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    _, mask = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    bubbles: List[Dict[str, float]] = []
    for c in contours:
        area = float(cv2.contourArea(c))
        if area < min_area:
            continue

        peri = float(cv2.arcLength(c, True))
        circularity = 0.0
        if peri > 1e-6:
            circularity = float((4.0 * np.pi * area) / (peri * peri))

        m = cv2.moments(c)
        if abs(m["m00"]) < 1e-6:
            continue
        cx = float(m["m10"] / m["m00"])
        cy = float(m["m01"] / m["m00"])
        x, y, w, h = cv2.boundingRect(c)

        # 接触线近似：取轮廓中 y 最大的点附近，计算左右接触点
        pts = c.reshape(-1, 2)
        max_y = float(pts[:, 1].max())
        contact_band = pts[pts[:, 1] >= max_y - 2]
        left_x = float(contact_band[:, 0].min()) if len(contact_band) else float(x)
        right_x = float(contact_band[:, 0].max()) if len(contact_band) else float(x + w)
        contact_width = max(1e-6, right_x - left_x)
        contact_angle = float(max(3.0, min(177.0, 180.0 - 110.0 * (h / max(1.0, float(w))))))

        bubbles.append(
            {
                "area_px": area,
                "circularity": circularity,
                "cx": cx,
                "cy": cy,
                "bbox_w": float(w),
                "bbox_h": float(h),
                "contact_line_y": max_y,
                "contact_line_width_px": contact_width,
                "contact_angle_deg": contact_angle,
            }
        )

    return sorted(bubbles, key=lambda x: x["area_px"], reverse=True)


def _attach_velocity_and_direction(prev_bubbles: List[Dict[str, float]], curr_bubbles: List[Dict[str, float]]) -> None:
    try:
        import numpy as np  # type: ignore
    except Exception:
        return

    if not prev_bubbles or not curr_bubbles:
        return

    used_prev = set()
    for b in curr_bubbles:
        best_idx = -1
        best_dist = float("inf")
        for idx, pb in enumerate(prev_bubbles):
            if idx in used_prev:
                continue
            d = float(np.hypot(b["cx"] - pb["cx"], b["cy"] - pb["cy"]))
            if d < best_dist:
                best_dist = d
                best_idx = idx

        if best_idx < 0:
            continue
        used_prev.add(best_idx)
        pb = prev_bubbles[best_idx]
        dx = float(b["cx"] - pb["cx"])
        dy = float(b["cy"] - pb["cy"])
        b["velocity_px_per_frame"] = float(np.hypot(dx, dy))
        b["velocity_dx"] = dx
        b["velocity_dy"] = dy
        b["direction_deg"] = float(np.degrees(np.arctan2(dy, dx)))

        contact_shift = abs(b["contact_line_width_px"] - pb.get("contact_line_width_px", b["contact_line_width_px"]))
        b["pinning_suspected"] = bool(b.get("velocity_px_per_frame", 0.0) > 1.0 and contact_shift < 1.2)


def run_nanomechanics_bubble_suite(frame, prev_frame=None) -> Dict[str, object]:
    """气泡追踪分析：用于电渗流/电泳驱动下的运动与接触线特征检测。"""

    out: Dict[str, object] = {}
    curr_bubbles = _extract_bubbles(frame)
    if not curr_bubbles:
        return out

    out["bubble_count"] = len(curr_bubbles)
    out["bubbles"] = curr_bubbles

    if prev_frame is not None:
        prev_bubbles = _extract_bubbles(prev_frame)
        _attach_velocity_and_direction(prev_bubbles, curr_bubbles)
        out["prev_bubble_count"] = len(prev_bubbles)

        if len(prev_bubbles) == 1 and len(curr_bubbles) >= 2:
            px = prev_bubbles[0]["cx"]
            py = prev_bubbles[0]["cy"]
            near_cnt = sum(1 for b in curr_bubbles if ((b["cx"] - px) ** 2 + (b["cy"] - py) ** 2) ** 0.5 < 45)
            out["bubble_split_detected"] = near_cnt >= 2

    return out
