# piside/edge_vision/motion_detector.py
import cv2
import time


class EdgeMotionDetector:
    """边缘端：物理运动与异象检测引擎 (抗光线干扰强化版)"""

    def __init__(self, cooldown=15.0):  # 默认直接调高到15秒冷却
        # 1. 调高 varThreshold (从40提高到100)，让算法忽略微弱的光线闪烁
        self.bg_subtractor = cv2.createBackgroundSubtractorMOG2(history=300, varThreshold=100, detectShadows=False)
        self.last_event_time = 0
        self.cooldown = cooldown

    def process_frame(self, frame, policies):
        if not policies:
            return None, None

        current_time = time.time()
        if current_time - self.last_event_time < self.cooldown:
            return None, None

        # 2. ★ 核心降噪：先给画面加上严重的高斯模糊，把细小的噪点全部抹平！
        blurred_frame = cv2.GaussianBlur(frame, (21, 21), 0)

        # 使用模糊后的画面去比对背景
        fg_mask = self.bg_subtractor.apply(blurred_frame)
        contours, _ = cv2.findContours(fg_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        motion_bbox = None
        for contour in contours:
            # 3. ★ 提高触发面积：把 5000 改为 30000（意味着必须是明显的人体或大物体移动才触发）
            if cv2.contourArea(contour) > 30000:
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

                    # 裁切时依然使用原图（frame），保证发给大模型的图片是清晰的
                    crop_img = frame[y1:y2, x1:x2]
                    self.last_event_time = current_time
                    return policy["event_name"], crop_img

        return None, None