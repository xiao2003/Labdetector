from __future__ import annotations

import importlib
from typing import Dict, List

from pc.core.base_expert import BaseExpert


class EquipmentOCRExpert(BaseExpert):
    """设备 OCR 识别专家。"""

    def __init__(self) -> None:
        self.reader = None
        self.is_loaded = False

    @property
    def expert_name(self) -> str:
        return "设备 OCR 识别专家"

    @property
    def expert_version(self) -> str:
        return "3.0.2"

    def supported_events(self) -> List[str]:
        return ["ocr_read", "读取仪表"]

    def get_edge_policy(self) -> Dict:
        return {}

    def match_event(self, event_name: str) -> bool:
        return event_name in self.supported_events()

    def _lazy_load(self) -> None:
        if self.is_loaded:
            return
        try:
            from pc.core.logger import console_info

            console_info("正在唤起 [设备 OCR 识别专家]，按需加载 OCR 依赖。")
            easyocr = importlib.import_module("easyocr")
            torch = importlib.import_module("torch")
            self.reader = easyocr.Reader(["ch_sim", "en"], gpu=bool(torch.cuda.is_available()))
            self.is_loaded = True
        except Exception:
            from pc.core.logger import console_error

            console_error("设备 OCR 依赖未就绪，请在专家模型管理中导入 OCR 模型或补齐 easyocr / torch。")
            self.reader = None
            self.is_loaded = False

    def _lazy_unload(self) -> None:
        if not self.is_loaded:
            return
        self.reader = None
        try:
            torch = importlib.import_module("torch")
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass
        self.is_loaded = False

    def analyze(self, frame, context) -> str:
        self._lazy_load()

        text_extracted = ""
        if self.reader is not None and frame is not None:
            try:
                results = self.reader.readtext(frame)
                text_extracted = " ".join(res[1] for res in results if len(res) > 1)
            except Exception:
                text_extracted = ""

        self._lazy_unload()

        if text_extracted.strip():
            return f"设备 OCR 识别结果：{text_extracted}"
        return "当前未能稳定识别画面中的仪表读数或设备文字。"
