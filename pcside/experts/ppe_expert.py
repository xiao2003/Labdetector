# pcside/experts/ppe_expert.py
import cv2
from pcside.core.base_expert import BaseExpert
from pcside.core.logger import console_info, console_error

try:
    from ultralytics import YOLO

    HAS_YOLO = True
except ImportError:
    HAS_YOLO = False


class PPEExpert(BaseExpert):
    def __init__(self):
        super().__init__()
        self.model = None
        # 实际部署时，这里替换为你自己用 lab 图像微调过的 yolov8n-ppe.pt 模型路径
        self.model_path = "yolov8n.pt"

    @property
    def expert_name(self):
        return "个人防护装备(PPE)规范专家"

    def get_edge_policy(self):
        # 让树莓派不仅在发生异动时截图，还要尽量给出全身框
        return {
            "event_name": "Motion_Alert",
            "trigger": ["Pixel_Motion_Active"],
            "crop_strategy": "motion_bounding_box",
            "padding": 0.5  # 扩大裁剪范围，把人的全身拍进去
        }

    def match_event(self, event_name):
        return event_name == "Motion_Alert"

    def analyze(self, frame, context):
        if not HAS_YOLO:
            return ""

        if self.model is None:
            try:
                console_info(f"[{self.expert_name}] 正在懒加载 YOLO 轻量级模型...")
                self.model = YOLO(self.model_path)
            except Exception as e:
                console_error(f"[{self.expert_name}] YOLO加载失败: {e}")
                return ""

        # 运行快速目标检测 (置信度设为0.5)
        results = self.model(frame, verbose=False, conf=0.5)

        # 提取检测到的类别
        detected_classes = []
        for r in results:
            for c in r.boxes.cls:
                detected_classes.append(self.model.names[int(c)])

        # 【核心业务逻辑】
        # 假设你的微调模型中，类别 0 是 person(人), 1 是 bare_hands(裸手), 2 是 no_mask(未戴口罩)
        # 这里用标准 COCO 类别 'person' 演示逻辑：
        if 'person' in detected_classes:
            # 伪代码：如果你训练了裸手检测
            if 'bare_hands' in detected_classes:
                return "严重警告：检测到人员操作时未佩戴丁腈手套，请立即规范穿戴！"

            # 如果一切正常，返回空字符串，系统静默不打扰
            return ""

        # 没检测到人，不发声
        return ""