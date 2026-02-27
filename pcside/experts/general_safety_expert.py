# pcside/experts/general_safety_expert.py
from pcside.core.base_expert import BaseExpert

class GeneralSafetyExpert(BaseExpert):
    @property
    def expert_name(self) -> str: return "通用安防专家"

    def get_edge_policy(self) -> dict:
        # 策略 1：要求树莓派同时看到“人”和“手机”时触发，并回传完整的高清大图供大模型归档
        return {
            "event_name": "安防违规-使用手机",
            "trigger_classes": ["person", "cell phone"],
            "condition": "all",        # 必须同时存在
            "action": "full_frame",    # 回传全图
            "cooldown": 10.0           # 10秒冷却
        }

    def match_event(self, event_name: str) -> bool:
        return event_name == "安防违规-使用手机"

    def analyze(self, frame, context) -> str:
        # frame 是树莓派传来的全图
        # 这里调用大模型生成日志...
        return "警告：已检测到违规在实验台使用手机，请立即停止！"