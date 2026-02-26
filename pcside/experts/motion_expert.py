# pcside/experts/motion_expert.py
from pcside.core.base_expert import BaseExpert
from pcside.core.ai_backend import analyze_image
import pcside.core.ai_backend as ai_be


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
        # 动态获取当前选中的模型
        model = ai_be._STATE.get("selected_model", "llava:7b-v1.5-q4_K_M")

        # 真正调用大模型去分析传过来的关键帧
        result = analyze_image(frame, model)

        # 组装专家报告，准备让喇叭播报
        if result and result != "识别失败":
            return f"报告，监控画面显示：{result}"
        else:
            return "发现异动，但画面分析失败。"