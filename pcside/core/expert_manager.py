# pcside/core/expert_manager.py
import os
import importlib
import inspect
from pcside.core.base_expert import BaseExpert
from pcside.core.logger import console_info, console_error

class ExpertManager:
    def __init__(self):
        self.experts = []
        self._load_all_experts()

    def _load_all_experts(self):
        """动态加载 pcside/experts 目录下的所有插件"""
        experts_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'experts')
        if not os.path.exists(experts_dir):
            os.makedirs(experts_dir, exist_ok=True)
            open(os.path.join(experts_dir, '__init__.py'), 'a').close()
            return

        for filename in os.listdir(experts_dir):
            if filename.endswith(".py") and not filename.startswith("__"):
                module_name = f"pcside.experts.{filename[:-3]}"
                try:
                    module = importlib.import_module(module_name)
                    for name, obj in inspect.getmembers(module, inspect.isclass):
                        if issubclass(obj, BaseExpert) and obj is not BaseExpert:
                            instance = obj()
                            self.experts.append(instance)
                            console_info(f"成功加载专家插件: [{instance.expert_name}]")
                except Exception as e:
                    console_error(f"加载插件 {filename} 失败: {e}")

    def get_aggregated_edge_policy(self) -> dict:
        """汇总策略下发给树莓派"""
        policies = [expert.get_edge_policy() for expert in self.experts if expert.get_edge_policy()]
        return {"event_policies": policies}

    def route_and_analyze(self, event_name: str, frame, context: dict) -> str:
        """将画面派发给匹配的专家"""
        for expert in self.experts:
            if expert.match_event(event_name):
                return expert.analyze(frame, context)
        return ""

expert_manager = ExpertManager()