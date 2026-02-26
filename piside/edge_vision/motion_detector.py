# piside/edge_vision/motion_detector.py
import cv2
import time


class EdgeMotionDetector:
    """边缘端：物理运动与异象检测引擎"""

    def __init__(self, cooldown=3.0):
        self.bg_subtractor = cv2.createBackgroundSubtractorMOG2(history=300, varThreshold=40, detectShadows=False)
        self.last_event_time = 0
        self.cooldown = cooldown

    def process_frame(self, frame, policies):
        if not policies:
            return None, None

        current_time = time.time()
        if current_time - self.last_event_time < self.cooldown:
            return None, None

        fg_mask = self.bg_subtractor.apply(frame)
        contours, _ = cv2.findContours(fg_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        motion_bbox = None
        for contour in contours:
            if cv2.contourArea(contour) > 5000:  # 过滤小噪点
                motion_bbox = cv2.boundingRect(contour)
                break

        if motion_bbox:
            for policy in policies:
                if "Pixel_Motion_Active" in policy.get("trigger", []):
                    x, y, w, h = motion_bbox
                    pad = policy.get("padding", 0.0)

                    img_h, img_w = frame.shape[:2]
                    x1 = max(0, int(x - w * pad))
                    y1 = max(0, int(y - h * pad))
                    x2 = min(img_w, int(x + w * (1 + pad)))
                    y2 = min(img_h, int(y + h * (1 + pad)))

                    crop_img = frame[y1:y2, x1:x2]
                    self.last_event_time = current_time
                    return policy["event_name"], crop_img

        return None, None