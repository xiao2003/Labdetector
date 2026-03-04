# pcside/core/expert_manager.py
import importlib
import inspect
import os
from typing import Any, Dict, List

from pcside.core.base_expert import BaseExpert
from pcside.core.config import get_config, set_config
from pcside.core.logger import console_error, console_info


class ExpertManager:
    def __init__(self):
        self.experts: Dict[str, BaseExpert] = {}
        self.load_experts()

    def load_experts(self):
        self.experts.clear()
        experts_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "experts")
        if not os.path.exists(experts_dir):
            console_error(f"未找到专家目录: {experts_dir}")
            return

        console_info("===== 正在扫描并加载专家模型 =====")
        for filename in sorted(os.listdir(experts_dir)):
            if not filename.endswith(".py") or filename.startswith("__"):
                continue

            module_name = filename[:-3]
            config_key = f"experts.{module_name}"
            is_enabled = get_config(config_key, -1)
            if is_enabled == -1:
                set_config(config_key, 1)
                is_enabled = 1
            if str(is_enabled) == "0" or is_enabled is False:
                console_info(f"已禁用: [{module_name}.py] (配置项为 0)")
                continue

            try:
                module = importlib.import_module(f"pcside.experts.{module_name}")
                for _, obj in inspect.getmembers(module, inspect.isclass):
                    if issubclass(obj, BaseExpert) and obj is not BaseExpert:
                        expert_instance = obj()
                        self.experts[expert_instance.expert_name] = expert_instance
                        console_info(
                            f"已启用: [{expert_instance.expert_name}] "
                            f"v{expert_instance.expert_version} ({module_name}.py)"
                        )
            except Exception as e:
                console_error(f"加载专家 [{module_name}] 失败: {e}")

        console_info(f"===== 共成功加载 {len(self.experts)} 个专家 =====\n")

    def get_aggregated_edge_policy(self) -> Dict[str, Any]:
        policies: List[Dict[str, Any]] = []
        for expert in self.experts.values():
            p = expert.get_edge_policy()
            if not p:
                continue
            if isinstance(p, list):
                policies.extend([x for x in p if isinstance(x, dict)])
            elif isinstance(p, dict):
                policies.append(p)
        return {"event_policies": policies}

    def route_and_analyze(self, event_name: str, frame: Any, context: Dict[str, Any]) -> str:
        results = []
        for expert in self.experts.values():
            if expert.match_event(event_name):
                try:
                    enriched = dict(context or {})
                    enriched.setdefault("event_name", event_name)
                    enriched.setdefault("expert", expert.expert_name)
                    res = expert.analyze(frame, enriched)
                    if res:
                        results.append(res)
                except Exception as e:
                    console_error(f"专家 [{expert.expert_name}] 分析异常: {e}")
        return " ".join(results) if results else ""

    def run_self_checks(self) -> List[Dict[str, Any]]:
        reports = []
        for expert in self.experts.values():
            try:
                reports.append(expert.self_check())
            except Exception as e:
                reports.append({"expert": expert.expert_name, "status": "error", "error": str(e)})
        return reports


expert_manager = ExpertManager()
