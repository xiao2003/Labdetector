import os
from typing import Dict, List

from pcside.core.base_expert import BaseExpert
from pcside.core.config import get_config
from pcside.experts.utils import parse_detected_classes, safe_upper_tokens


class ChemSafetyExpert(BaseExpert):
    """实验室危化品识别提醒专家。"""

    @property
    def expert_name(self) -> str:
        return "实验室危化品识别提醒专家"

    @property
    def expert_version(self) -> str:
        return "2.5"

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
        # 轻量本地规则；如果未来有结构化文件，可用 kb_builder 导入并扩展。
        return {
            "HF": "高危：检测到氢氟酸（HF），必须佩戴面罩+耐酸手套。",
            "H2SO4": "警告：检测到硫酸，请检查护目镜与防酸围裙。",
            "HNO3": "警告：检测到硝酸，注意通风柜操作并远离有机物。",
            "NAOH": "警告：检测到氢氧化钠，注意碱液飞溅风险。",
            "METHANOL": "警告：检测到甲醇，注意易燃与吸入危害。",
            "ETHANOL": "提示：检测到乙醇，注意明火与静电点火风险。",
            "ACETONE": "警告：检测到丙酮，需加强通风并远离热源。",
        }

    def _extract_text(self, frame) -> str:
        # 可选 OCR，缺失依赖时自动降级。
        try:
            import easyocr  # type: ignore

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
                # 与 PPE 结合做闭环提醒
                if chem == "HF" and "glove" not in detected and "gloves" not in detected:
                    return "极度危险：识别到 HF 且未检测到手套，请立即停止操作并上报。"
                return tip

        # 结构化KB补充（例如危化品目录表）
        try:
            from pcside.knowledge_base.structured_kb import get_default_structured_kb

            sk = get_default_structured_kb()
            for token in token_set:
                rows = sk.search(token, limit=2)
                if rows:
                    return f"危化品知识库提醒：{rows[0]['name']} - {rows[0]['value'][:80]}"
        except Exception:
            pass

        if "bottle" in detected and ("glove" not in detected and "gloves" not in detected):
            return "提示：检测到试剂瓶操作，建议确认已佩戴手套与护目镜。"

        return ""
