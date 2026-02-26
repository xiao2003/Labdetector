# pcside/experts/danger_expert.py
from pcside.core.base_expert import BaseExpert
import pcside.core.ai_backend as ai_be


class DangerBehaviorExpert(BaseExpert):
    @property
    def expert_name(self):
        return "危险行为与溢出检测专家"

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
        model = ai_be._STATE.get("selected_model", "llava:7b-v1.5-q4_K_M")

        # ★ 精心打磨的工业级 Prompt：杜绝神经病式播报
        # 让它专注于“危险动作”和“化学品泄漏”
        custom_prompt = """
        你是一个微纳流控实验室安全审核员。请检查画面是否存在以下两类危险：
        1. 危险姿势：人员在实验台前趴着睡觉、异常跌倒、双手脱离高风险设备。
        2. 物品异常：试剂瓶倾倒、桌面出现不明液体反光（疑似泄漏）、起火或烟雾。
        如果存在上述情况，请用15个字以内发出严厉警告。
        如果画面只是正常走动、拿取物品、写字、或是没有人的墙壁/噪点，请务必直接回复“无明显异常”。
        """

        # 调用 AI 底层接口
        result = ai_be.analyze_image(frame, model, prompt=custom_prompt)

        # ★ 静音拦截：只有真正危险时才开口
        if result and "无明显异常" in result:
            return ""

        if result and result != "识别失败":
            return f"实验室安全警告：{result}"

        return ""