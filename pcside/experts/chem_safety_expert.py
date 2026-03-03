# pcside/experts/chem_safety_expert.py
import os

import easyocr
import pandas as pd

from pcside.core.base_expert import BaseExpert
from pcside.core.config import get_config
from pcside.core.logger import console_error


class ChemSafetyExpert(BaseExpert):
    def __init__(self):
        super().__init__()
        self.reader = easyocr.Reader(['ch_sim', 'en'], gpu=True)
        self.kb_df = self._load_chem_kb()

    def _load_chem_kb(self):
        kb_path = get_config("knowledge_base.chemical_catalog", "pcside/knowledge_base/chemical_safety.xlsx")
        if not os.path.exists(kb_path):
            return None
        try:
            return pd.read_excel(kb_path)
        except Exception as e:
            console_error(f"危化品知识库加载失败: {e}")
            return None

    @property
    def expert_name(self) -> str:
        return "危化品管控专家"

    def get_edge_policy(self) -> dict:
        return {
            "event_name": "危化品识别",
            "trigger_classes": ["bottle"],
            "condition": "any",
            "action": "crop_target",
            "cooldown": 5.0
        }

    def match_event(self, event_name: str) -> bool:
        return event_name == "危化品识别"

    def analyze(self, frame, context) -> str:
        detected_raw = context.get("detected_classes", "")
        detected_all = detected_raw.split(",") if isinstance(detected_raw, str) else detected_raw

        text_on_bottle = "".join(self.reader.readtext(frame, detail=0)).upper()

        if "HF" in text_on_bottle and "glove" not in detected_all:
            return "极度危险：检测到氢氟酸操作未佩戴手套，请立即终止！"

        if self.kb_df is not None and "化学品" in self.kb_df.columns and "风险提示" in self.kb_df.columns:
            for _, row in self.kb_df.iterrows():
                chem = str(row["化学品"]).upper()
                if chem and chem in text_on_bottle:
                    return str(row["风险提示"])

        return ""