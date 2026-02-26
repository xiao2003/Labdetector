# pcside/core/base_expert.py
from abc import ABC, abstractmethod
import numpy as np
from typing import Dict, Any


class BaseExpert(ABC):
    """LabDetector V3.0 实验操作专家模型的标准基类"""

    @property
    @abstractmethod
    def expert_name(self) -> str:
        """插件名称"""
        pass

    @abstractmethod
    def get_edge_policy(self) -> Dict[str, Any]:
        """向边缘端下发的画面截取策略"""
        pass

    @abstractmethod
    def match_event(self, event_name: str) -> bool:
        """路由匹配逻辑"""
        pass

    @abstractmethod
    def analyze(self, frame: np.ndarray, context: dict) -> str:
        """核心分析逻辑，返回需要语音播报的警告文本"""
        pass