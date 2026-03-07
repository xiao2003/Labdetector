from __future__ import annotations

import importlib
from typing import Dict, List

from pc.core.base_expert import BaseExpert
from pc.experts.utils import parse_detected_classes, safe_upper_tokens


class ChemSafetyExpert(BaseExpert):
    """实验室危化品识别提醒专家。"""

    @property
    def expert_name(self) -> str:
        return "实验室危化品识别提醒专家"

    @property
    def expert_version(self) -> str:
        return "2.7.0"

    def supported_events(self) -> List[str]:
        return ["危化品识别", "化学品容器识别"]

    def get_edge_policy(self) -> Dict:
        return {
            "event_name": "危化品识别",
            "trigger_classes": ["bottle", "chemical bottle", "reagent bottle"],
            "condition": "any",
            "action": "crop_target",
            "cooldown": 4.0,
        }

    def match_event(self, event_name: str) -> bool:
        return event_name in self.supported_events()

    def _load_hazard_map(self):
        return {
            "HF": "高危：检测到氢氟酸（HF），必须佩戴面罩和耐酸手套。",
            "H2SO4": "警告：检测到硫酸，请检查护目镜与防酸围裙。",
            "HNO3": "警告：检测到硝酸，注意通风柜操作并远离有机物。",
            "NAOH": "警告：检测到氢氧化钠，注意碱液飞溅风险。",
            "METHANOL": "警告：检测到甲醇，注意易燃与吸入危害。",
            "ETHANOL": "提示：检测到乙醇，注意明火与静电点火风险。",
            "ACETONE": "警告：检测到丙酮，需加强通风并远离热源。",
        }

    def _extract_text(self, frame) -> str:
        try:
            easyocr = importlib.import_module("easyocr")
            reader = easyocr.Reader(["ch_sim", "en"], gpu=False)
            return " ".join(reader.readtext(frame, detail=0))
        except Exception:
            return ""

    def analyze(self, frame, context) -> str:
        detected = parse_detected_classes(context.get("detected_classes", ""))
        text = self._extract_text(frame)
        token_set = set(safe_upper_tokens(text))

        hazard_map = self._load_hazard_map()
        for chem, tip in hazard_map.items():
            if chem in token_set or chem in text.upper():
                if chem == "HF" and "glove" not in detected and "gloves" not in detected:
                    return "极度危险：识别到 HF 且未检测到手套，请立即停止操作并上报。"
                return tip

        structured_rows = context.get("knowledge_structured_rows") or []
        for row in structured_rows:
            row_name = str(row.get("name", "")).upper()
            row_value = str(row.get("value", ""))
            if any(token and token in row_name for token in token_set):
                return f"危化品知识库提醒：{row.get('name')} - {row_value[:120]}"

        try:
            from pc.knowledge_base.rag_engine import knowledge_manager

            for token in token_set:
                bundle = knowledge_manager.build_scope_bundle(token, self.knowledge_scope, top_k=2)
                rows = bundle.get("structured_rows") or []
                if rows:
                    row = rows[0]
                    return f"危化品知识库提醒：{row['name']} - {str(row['value'])[:120]}"
        except Exception:
            pass

        if "bottle" in detected and ("glove" not in detected and "gloves" not in detected):
            return "提示：检测到试剂瓶操作，建议确认已佩戴手套与护目镜。"

        return ""
