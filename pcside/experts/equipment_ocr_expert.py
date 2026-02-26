# pcside/experts/equipment_ocr_expert.py
import cv2
import numpy as np
from pcside.core.base_expert import BaseExpert
from pcside.core.logger import console_info
import pcside.core.ai_backend as ai_be

try:
    import easyocr

    HAS_OCR = True
except ImportError:
    HAS_OCR = False


class EquipmentOCRExpert(BaseExpert):
    def __init__(self):
        super().__init__()
        self.reader = None

    @property
    def expert_name(self):
        return "精密设备状态读取专家"

    def get_edge_policy(self):
        return {
            # 让边缘端定时发送，而不是基于动作（设备屏幕数字变化通常没有物理运动）
            "event_name": "Equipment_Status_Sync",
            "trigger": ["Timer_10s"],  # 假设我们在树莓派上加了一个每10秒触发一次的策略
            "crop_strategy": "full_frame",
            "padding": 0.0
        }

    def match_event(self, event_name):
        return event_name in ["Equipment_Status_Sync", "Motion_Alert"]

    def analyze(self, frame, context):
        if not HAS_OCR:
            return ""

        if self.reader is None:
            console_info(f"[{self.expert_name}] 正在加载 EasyOCR 引擎...")
            self.reader = easyocr.Reader(['en'], gpu=True)  # 使用 GPU 加速英文和数字识别

        # 1. 提取画面中的文本
        ocr_results = self.reader.readtext(frame, detail=0)
        text_content = " ".join(ocr_results).upper()

        if not text_content:
            return ""

        # 2. 核心业务逻辑：基于关键字的极速拦截
        if "ERROR" in text_content or "FAIL" in text_content or "STOP" in text_content:
            return f"设备警报：检测到屏幕显示异常字眼。提取内容为：{text_content[:20]}"

        # 3. 智能联动：如果数字看起来不对劲，丢给大模型去分析
        if "ML/MIN" in text_content or "UL/MIN" in text_content:
            model = ai_be._STATE.get("selected_model", "qwen-vl-max")
            prompt = f"屏幕OCR提取文本为[{text_content}]。作为微纳流控专家，请判断这个流速数值是否在正常安全范围内？如果异常请用15个字以内警告，如果正常请回复'无明显异常'。"

            ai_result = ai_be.analyze_image(frame, model, prompt=prompt)
            if ai_result and "无明显异常" not in ai_result:
                return f"流速监控提示：{ai_result}"

        return ""