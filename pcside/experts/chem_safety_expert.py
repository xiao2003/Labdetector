# pcside/experts/chem_safety_expert.py
from pcside.core.base_expert import BaseExpert
import pandas as pd
import easyocr


class ChemSafetyExpert(BaseExpert):
    def __init__(self):
        super().__init__()
        self.reader = easyocr.Reader(['ch_sim', 'en'], gpu=True)
        self.kb_df = pd.read_excel("pcside/knowledge_base/chemical_safety.xlsx")

    @property
    def expert_name(self) -> str: return "危化品管控专家"

    def get_edge_policy(self) -> dict:
        # 策略 2：要求树莓派只要看到“瓶子”就触发。
        # 极致省带宽：只要求回传瓶子所在的“局部裁剪图(crop_target)”用来做 OCR 即可！
        return {
            "event_name": "危化品识别",
            "trigger_classes": ["bottle"],
            "condition": "any",  # 有任意一个就触发
            "action": "crop_target",  # 仅裁剪目标区域回传
            "cooldown": 5.0  # 5秒冷却
        }

    def match_event(self, event_name: str) -> bool:
        return event_name == "危化品识别"

    def analyze(self, frame, context) -> str:
        # ★ 神奇之处：这时的 frame 只有几十KB，是树莓派精准裁剪的“瓶子特写图”！
        # 但 context 里包含了树莓派顺便发来的全局视野元数据（比如有没有手套）
        detected_all = context.get("detected_classes", [])

        # 1. OCR 极速读取瓶身上的文字
        text_on_bottle = "".join(self.reader.readtext(frame, detail=0)).upper()

        # 2. 查 Excel 知识库 (假设读出了 "HF")
        # 如果是氢氟酸，且 detected_all 里没有 "glove"
        if "HF" in text_on_bottle and "glove" not in detected_all:
            return "极度危险：检测到氢氟酸操作未佩戴手套，请立即终止！"

        return ""