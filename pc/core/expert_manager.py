from __future__ import annotations

import importlib
import inspect
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List

from pc.core.base_expert import BaseExpert
from pc.core.config import get_config, set_config
from pc.core.expert_registry import (
    expert_asset_dir,
    get_expert_definition,
    list_expert_definitions,
)
from pc.core.logger import console_error, console_info

try:
    from pc.knowledge_base.rag_engine import knowledge_manager
except Exception:
    knowledge_manager = None


class ExpertManager:
    def __init__(self) -> None:
        self.experts: Dict[str, BaseExpert] = {}
        self._expert_codes: Dict[str, str] = {}
        self.load_experts()

    def load_experts(self) -> None:
        self.experts.clear()
        self._expert_codes.clear()

        console_info("===== 正在加载专家模块 =====")
        for definition in list_expert_definitions():
            config_key = f"experts.{definition.code}"
            enabled = get_config(config_key, -1)
            if enabled == -1:
                legacy_key = f"experts.{definition.code.split('.')[-1]}"
                legacy_enabled = get_config(legacy_key, -1)
                if legacy_enabled != -1:
                    enabled = legacy_enabled
                else:
                    set_config(config_key, 1)
                    enabled = 1

            if str(enabled) == "0" or enabled is False:
                console_info(f"跳过 [{definition.display_name}] ({definition.code})")
                continue

            try:
                module = importlib.import_module(definition.module)
                loaded = False
                for _, obj in inspect.getmembers(module, inspect.isclass):
                    if issubclass(obj, BaseExpert) and obj is not BaseExpert:
                        instance = obj()
                        self.experts[instance.expert_name] = instance
                        self._expert_codes[instance.expert_name] = definition.code
                        console_info(
                            f"已加载 [{instance.expert_name}] v{instance.expert_version} ({definition.code})"
                        )
                        loaded = True
                if not loaded:
                    console_error(f"专家模块未发现可实例化对象: {definition.code}")
            except Exception as exc:
                console_error(f"加载失败 [{definition.code}] 异常: {exc}")

        console_info(f"===== 已加载 {len(self.experts)} 个专家 =====\n")

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

    def route_and_analyze(self, event_name: str, frame: Any, context: Dict[str, Any]) -> str:
        results: List[str] = []
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

    def _asset_status(self, expert_code: str) -> Dict[str, Any]:
        asset_root = expert_asset_dir(expert_code)
        files = [path for path in asset_root.rglob("*") if path.is_file()]
        return {
            "path": str(asset_root),
            "file_count": len(files),
            "ready": bool(files),
            "latest_mtime": max((path.stat().st_mtime for path in files), default=0.0),
        }

    def list_knowledge_scopes(self) -> List[Dict[str, str]]:
        rows: List[Dict[str, str]] = []
        for expert in self.experts.values():
            rows.append(
                {
                    "expert_name": expert.expert_name,
                    "expert_code": expert.expert_code,
                    "scope": expert.knowledge_scope,
                }
            )
        return sorted(rows, key=lambda item: item["scope"])

    def list_experts_metadata(self) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for expert in self.experts.values():
            definition = get_expert_definition(expert.expert_code)
            events = [item for item in expert.supported_events() if str(item).strip()]
            rows.append(
                {
                    "expert_name": expert.expert_name,
                    "expert_code": expert.expert_code,
                    "expert_version": expert.expert_version,
                    "events": events,
                    "knowledge_scope": expert.knowledge_scope,
                    "display_name": definition.display_name if definition else expert.expert_name,
                    "description": definition.description if definition else "",
                    "knowledge_required": bool(definition.knowledge_required) if definition else False,
                    "model_required": bool(definition.model_required) if definition else False,
                    "model_hint": definition.model_hint if definition else "",
                    "knowledge_hint": definition.knowledge_hint if definition else "",
                    "media_types": list(definition.media_types) if definition else [],
                }
            )
        return sorted(rows, key=lambda item: item["expert_code"])

    def list_expert_catalog(self) -> List[Dict[str, Any]]:
        scope_rows = {}
        if knowledge_manager is not None:
            try:
                for row in knowledge_manager.list_scopes(include_known_experts=True):
                    scope_rows[row["scope"]] = row
            except Exception:
                scope_rows = {}

        rows: List[Dict[str, Any]] = []
        loaded_by_code = {expert.expert_code: expert for expert in self.experts.values()}
        for definition in list_expert_definitions():
            loaded = loaded_by_code.get(definition.code)
            asset_status = self._asset_status(definition.code)
            scope_row = scope_rows.get(definition.scope, {})
            rows.append(
                {
                    "expert_code": definition.code,
                    "display_name": definition.display_name,
                    "category": definition.category,
                    "description": definition.description,
                    "knowledge_scope": definition.scope,
                    "knowledge_title": scope_row.get("title", ""),
                    "knowledge_required": definition.knowledge_required,
                    "model_required": definition.model_required,
                    "model_hint": definition.model_hint,
                    "knowledge_hint": definition.knowledge_hint,
                    "media_types": list(definition.media_types),
                    "loaded": loaded is not None,
                    "expert_name": loaded.expert_name if loaded else definition.display_name,
                    "expert_version": loaded.expert_version if loaded else "",
                    "events": loaded.supported_events() if loaded else [],
                    "asset_path": asset_status["path"],
                    "asset_file_count": asset_status["file_count"],
                    "asset_ready": asset_status["ready"],
                    "knowledge_doc_count": int(scope_row.get("doc_count", 0) or 0),
                    "knowledge_ready": bool(
                        scope_row.get("doc_count", 0) or scope_row.get("vector_ready") or scope_row.get("structured_ready")
                    ),
                }
            )
        return rows

    def import_expert_assets(self, expert_code: str, paths: List[str]) -> Dict[str, Any]:
        definition = get_expert_definition(expert_code)
        if definition is None:
            raise ValueError(f"未知专家编码: {expert_code}")

        target_root = expert_asset_dir(expert_code)
        imported: List[str] = []
        failed: List[str] = []

        for raw_path in paths:
            source = Path(raw_path)
            if not source.exists():
                failed.append(str(source))
                continue
            target = target_root / source.name
            if source.resolve() == target.resolve():
                imported.append(source.name)
                continue
            if target.exists():
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                target = target_root / f"{target.stem}_{timestamp}{target.suffix}"
            try:
                if source.is_dir():
                    shutil.copytree(str(source), str(target))
                else:
                    shutil.copy2(str(source), str(target))
                imported.append(source.name)
            except Exception:
                failed.append(source.name)

        summary = {
            "expert_code": expert_code,
            "display_name": definition.display_name,
            "target_path": str(target_root),
            "imported": imported,
            "failed": failed,
            "imported_count": len(imported),
            "failed_count": len(failed),
        }
        if imported:
            console_info(
                f"专家资产导入完成 [{definition.display_name}]，成功 {summary['imported_count']} 项，失败 {summary['failed_count']} 项"
            )
        return summary

    def build_demo_sequence(self) -> List[Dict[str, Any]]:
        experts = self.list_expert_catalog()
        total = len(experts)
        sequence: List[Dict[str, Any]] = []
        for index, item in enumerate(experts, start=1):
            events = list(item.get("events") or [])
            primary_event = events[0] if events else "演示事件"
            description = item.get("description") or "展示专家规则、模型与知识库联动效果。"
            hint = f"【演示 {index}/{total}】{item['display_name']}：{description}"
            sequence.append(
                {
                    "index": index,
                    "total": total,
                    "expert_name": item["display_name"],
                    "expert_code": item["expert_code"],
                    "event_name": primary_event,
                    "knowledge_scope": item["knowledge_scope"],
                    "hint": hint,
                    "log": f"演示模式 [{index}/{total}] {item['display_name']} -> 事件[{primary_event}]：{description}",
                }
            )
        return sequence


expert_manager = ExpertManager()
