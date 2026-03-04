from abc import ABC, abstractmethod
from typing import Any, Dict, List


class BaseExpert(ABC):
    """统一专家插件接口（支持即插即用）。"""

    @property
    @abstractmethod
    def expert_name(self) -> str:
        pass

    @property
    def expert_version(self) -> str:
        return "1.0"

    def supported_events(self) -> List[str]:
        """可选：声明支持的事件名列表。"""
        return []

    @abstractmethod
    def get_edge_policy(self) -> Dict[str, Any] | List[Dict[str, Any]]:
        """返回边缘策略，可为单个 dict 或 dict 列表。"""
        pass

    @abstractmethod
    def match_event(self, event_name: str) -> bool:
        pass

    @abstractmethod
    def analyze(self, frame: Any, context: dict) -> str:
        pass

    def self_check(self) -> Dict[str, Any]:
        """本地自检接口，供测试脚本统一调用。"""
        return {
            "expert": self.expert_name,
            "version": self.expert_version,
            "status": "ok",
            "events": self.supported_events(),
        }
