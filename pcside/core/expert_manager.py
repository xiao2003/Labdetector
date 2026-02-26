# pcside/core/expert_manager.py
import os
import importlib
import inspect
from typing import Dict, Any

from pcside.core.base_expert import BaseExpert
from pcside.core.logger import console_info, console_error
from pcside.core.config import get_config, set_config


class ExpertManager:
    def __init__(self):
        self.experts: Dict[str, BaseExpert] = {}
        self.load_experts()

    def load_experts(self):
        self.experts.clear()
        # 动态定位到 experts 文件夹
        experts_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'experts')

        if not os.path.exists(experts_dir):
            console_error(f"未找到专家目录: {experts_dir}")
            return

        console_info("===== 正在扫描并加载专家模型 =====")

        # 遍历目录下的所有 .py 文件
        for filename in os.listdir(experts_dir):
            if filename.endswith('.py') and not filename.startswith('__'):
                module_name = filename[:-3]
                config_key = f"experts.{module_name}"

                # 1. 从配置文件中读取该专家的开关状态 (默认返回 -1 表示未记录)
                is_enabled = get_config(config_key, -1)

                # 2. 如果是第一次扫描到该专家，自动在配置中注册为 1 (开启)
                if is_enabled == -1:
                    set_config(config_key, 1)
                    is_enabled = 1

                # 3. 如果配置为 0 或 False，则跳过加载
                if str(is_enabled) == "0" or is_enabled is False:
                    console_info(f"已禁用: [{module_name}.py] (配置项为 0)")
                    continue

                # 4. 动态反射加载已启用的专家
                try:
                    module = importlib.import_module(f"pcside.experts.{module_name}")
                    for name, obj in inspect.getmembers(module, inspect.isclass):
                        # 找到继承自 BaseExpert 的具体类
                        if issubclass(obj, BaseExpert) and obj is not BaseExpert:
                            expert_instance = obj()
                            self.experts[expert_instance.expert_name] = expert_instance
                            console_info(f"已启用: [{expert_instance.expert_name}] ({module_name}.py)")
                except Exception as e:
                    console_error(f"加载专家 [{module_name}] 失败: {e}")

        console_info(f"===== 共成功加载 {len(self.experts)} 个专家 =====")

    def get_aggregated_edge_policy(self) -> Dict[str, Any]:
        """收集所有已启用专家的边缘端截帧策略，统一下发给树莓派"""
        policies = []
        for expert in self.experts.values():
            policy = expert.get_edge_policy()
            if policy:
                policies.append(policy)
        return {"event_policies": policies}

    def route_and_analyze(self, event_name: str, frame: Any, context: Dict[str, Any]) -> str:
        """接收到树莓派发来的事件后，路由给所有关心该事件的已启用专家"""
        results = []
        for expert in self.experts.values():
            if expert.match_event(event_name):
                try:
                    res = expert.analyze(frame, context)
                    if res:
                        results.append(res)
                except Exception as e:
                    console_error(f"专家 [{expert.expert_name}] 分析异常: {e}")

        # 将多个专家的结论合并返回 (静音拦截逻辑已在外层实现)
        if results:
            return " ".join(results)
        return ""


# 导出全局单例
expert_manager = ExpertManager()