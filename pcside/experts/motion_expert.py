# pcside/experts/motion_expert.py
from pcside.core.base_expert import BaseExpert

class MotionAlertExpert(BaseExpert):
    @property
    def expert_name(self):
        return "动态异象与行为监测专家"

    def get_edge_policy(self):
        return {
            "event_name": "Motion_Alert",
            "trigger": ["Pixel_Motion_Active"],
            "crop_strategy": "motion_bounding_box",
            "padding": 0.2
        }

    def match_event(self, event_name):
        return event_name == "Motion_Alert"

    def analyze(self, frame, context):
        # 实际开发时这里可调用大模型，目前直接返回文本测试闭环
        return "警告：检测到实验台存在未知的物理交互，请注意操作规范。"