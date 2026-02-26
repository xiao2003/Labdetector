from pcside.core.base_expert import BaseExpert
import pcside.core.ai_backend as ai_be
from pcside.core.logger import console_error


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

        # 极简且严厉的 Prompt，防止大模型陷入自我辩论的幻觉
        custom_prompt = """
        【严格指令】你是一个安防监控器。
        画面中是否发生以下事件：1.人员跌倒 2.人员趴在桌上睡觉 3.液体泄漏 4.起火冒烟。
        如果有，请只输出事件名称（例如：人员跌倒）。
        如果没有上述任何事件（包括正常走动、站立、空无一人），你【必须】只输出“无”这一个字。绝对禁止输出任何其他解释！
        """

        try:
            # 调用 AI 底层接口
            result = ai_be.analyze_image(frame, model, prompt=custom_prompt)

            # ★ 异常暴露：如果底层接口明确返回了失败
            if result == "识别失败" or result is None:
                console_error(f"[{self.expert_name}] 底层大模型请求超时或崩溃！请检查 Ollama 状态。")
                return ""

            clean_result = result.strip().lower()

            # 强化静音拦截：过滤掉大模型不听话产生的冗长废话
            if "无" == clean_result or "无明显异常" in clean_result or "正常" in clean_result or len(clean_result) > 20:
                # 哪怕它不听话输出了一大堆“我不认为存在...”，只要超过20个字，我们就认为它是幻觉废话，直接拦截。
                return ""

            return f"危险动作警报：{result}"

        except Exception as e:
            # ★ 确保专家内部的崩溃能在主程序日志中大声喊出来
            console_error(f"[{self.expert_name}] 执行过程中发生未捕获异常: {e}")
            return ""