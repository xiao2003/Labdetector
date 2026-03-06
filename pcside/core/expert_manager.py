# pcside/core/expert_manager.py
from __future__ import annotations

import importlib
import inspect
import os
from typing import Any, Dict, List

from pcside.core.base_expert import BaseExpert
from pcside.core.config import get_config, set_config
from pcside.core.logger import console_error, console_info

try:
    from pcside.knowledge_base.rag_engine import knowledge_manager
except Exception:
    knowledge_manager = None


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
        module_paths = []
        for root, _, files in os.walk(experts_dir):
            for filename in files:
                if not filename.endswith(".py") or filename.startswith("__"):
                    continue
                full_path = os.path.join(root, filename)
                rel = os.path.relpath(full_path, experts_dir)
                module_paths.append(rel[:-3].replace(os.sep, "."))

        for module_name in sorted(module_paths):
            config_key = f"experts.{module_name}"
            is_enabled = get_config(config_key, -1)
            if is_enabled == -1:
                legacy_key = f"experts.{module_name.split('.')[-1]}"
                legacy_enabled = get_config(legacy_key, -1)
                if legacy_enabled != -1:
                    is_enabled = legacy_enabled
                else:
                    set_config(config_key, 1)
                    is_enabled = 1
            if str(is_enabled) == "0" or is_enabled is False:
                console_info(f"已禁用 [{module_name}] (配置项为 0)")
                continue

            try:
                module = importlib.import_module(f"pcside.experts.{module_name}")
                for _, obj in inspect.getmembers(module, inspect.isclass):
                    if issubclass(obj, BaseExpert) and obj is not BaseExpert:
                        expert_instance = obj()
                        self.experts[expert_instance.expert_name] = expert_instance
                        console_info(
                            f"已启用 [{expert_instance.expert_name}] "
                            f"v{expert_instance.expert_version} ({module_name}.py)"
                        )
            except Exception as exc:
                console_error(f"加载专家 [{module_name}] 失败: {exc}")

        console_info(f"===== 共成功加载 {len(self.experts)} 个专家 =====\n")

    def get_aggregated_edge_policy(self) -> Dict[str, Any]:
        policies: List[Dict[str, Any]] = []
        for expert in self.experts.values():
            policy = expert.get_edge_policy()
            if not policy:
                continue
            if isinstance(policy, list):
                policies.extend(item for item in policy if isinstance(item, dict))
            elif isinstance(policy, dict):
                policies.append(policy)
        return {"event_policies": policies}

    def _build_knowledge_context(self, expert: BaseExpert, event_name: str, context: Dict[str, Any]) -> Dict[str, Any]:
        if knowledge_manager is None:
            return {}
        query = expert.build_knowledge_query(event_name, context)
        if not query.strip():
            return {
                "knowledge_scope": expert.knowledge_scope,
                "knowledge_scopes": ["common", expert.knowledge_scope],
                "knowledge_query": "",
                "knowledge_context": "",
                "knowledge_structured_rows": [],
                "knowledge_vector_hits": [],
            }
        try:
            bundle = knowledge_manager.build_scope_bundle(query, expert.knowledge_scope, top_k=3)
            return {
                "knowledge_scope": expert.knowledge_scope,
                "knowledge_scopes": bundle["scopes"],
                "knowledge_query": query,
                "knowledge_context": bundle["context"],
                "knowledge_structured_rows": bundle["structured_rows"],
                "knowledge_vector_hits": bundle["vector_hits"],
            }
        except Exception as exc:
            console_error(f"知识库检索失败 [{expert.expert_name}]: {exc}")
            return {
                "knowledge_scope": expert.knowledge_scope,
                "knowledge_scopes": ["common", expert.knowledge_scope],
                "knowledge_query": query,
                "knowledge_context": "",
                "knowledge_structured_rows": [],
                "knowledge_vector_hits": [],
            }

    def route_and_analyze(self, event_name: str, frame: Any, context: Dict[str, Any]) -> str:
        results = []
        for expert in self.experts.values():
            if expert.match_event(event_name):
                try:
                    enriched = dict(context or {})
                    enriched.setdefault("event_name", event_name)
                    enriched.setdefault("expert", expert.expert_name)
                    enriched.update(self._build_knowledge_context(expert, event_name, enriched))
                    response = expert.analyze(frame, enriched)
                    if response:
                        results.append(response)
                except Exception as exc:
                    console_error(f"专家 [{expert.expert_name}] 分析异常: {exc}")
        return " ".join(results) if results else ""

    def run_self_checks(self) -> List[Dict[str, Any]]:
        reports = []
        for expert in self.experts.values():
            try:
                reports.append(expert.self_check())
            except Exception as exc:
                reports.append({"expert": expert.expert_name, "status": "error", "error": str(exc)})
        return reports

    def list_knowledge_scopes(self) -> List[Dict[str, str]]:
        scopes = []
        for expert in self.experts.values():
            scopes.append(
                {
                    "expert_name": expert.expert_name,
                    "expert_code": expert.expert_code,
                    "scope": expert.knowledge_scope,
                }
            )
        return sorted(scopes, key=lambda item: item["scope"])


expert_manager = ExpertManager()
