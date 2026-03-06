import torch
from typing import Dict, List
from pcside.core.base_expert import BaseExpert


class EquipmentOCRExpert(BaseExpert):
    """实验室设备仪表OCR识别专家（符合 V2.6 极省显存规范）"""

    def __init__(self):
        self.reader = None
        self.is_loaded = False

    @property
    def expert_name(self) -> str:
        return "设备OCR识别专家"

    @property
    def expert_version(self) -> str:
        return "2.6.0"

    def supported_events(self) -> List[str]:
        # 只在触发特定任务时响应
        return ["ocr_read", "读取仪表"]

    def get_edge_policy(self) -> Dict:
        # OCR 通常由中心端语音指令主动触发，不需要边缘端发送主动策略
        return {}

    def match_event(self, event_name: str) -> bool:
        return event_name in self.supported_events()

    def _lazy_load(self):
        """动态载入显存 (Lazy Load)"""
        if not self.is_loaded:
            try:
                from pcside.core.logger import console_info
                console_info("正在唤醒 [设备 OCR 专家] 入显存...")
                import easyocr
                self.reader = easyocr.Reader(['ch_sim', 'en'], gpu=torch.cuda.is_available())
                self.is_loaded = True
            except ImportError:
                from pcside.core.logger import console_error
                console_error("缺少 easyocr 依赖，请在终端执行: pip install easyocr")

    def _lazy_unload(self):
        """用完立刻释放显存，保障本地大模型运行空间"""
        if self.is_loaded:
            self.reader = None
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            self.is_loaded = False
            from pcside.core.logger import console_info
            console_info("已释放 [设备 OCR 专家] 显存。")

    def analyze(self, frame, context) -> str:
        # 真正开始分析时，才临时加载模型
        self._lazy_load()

        text_extracted = ""
        if self.reader and frame is not None:
            results = self.reader.readtext(frame)
            text_extracted = " ".join([res[1] for res in results])

        # 提取完毕，立刻卸载
        self._lazy_unload()

        if text_extracted.strip():
            return f"OCR仪表读数识别结果为：{text_extracted}"
        return "未能清晰识别到视野内的仪表盘文字。"