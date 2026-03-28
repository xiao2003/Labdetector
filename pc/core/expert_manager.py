from __future__ import annotations

import importlib
import inspect
import shutil
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

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


VOICE_KEYWORD_FALLBACKS = {
    "safety.chem_safety_expert": (
        "化学品",
        "危化品",
        "试剂",
        "药品",
        "标签",
        "试剂瓶",
        "药液",
    ),
    "equipment_ocr_expert": (
        "ocr",
        "读数",
        "读一下",
        "识别设备",
        "仪表",
        "屏幕",
        "铭牌",
        "标签内容",
    ),
    "lab_qa_expert": (
        "什么",
        "为什么",
        "如何",
        "介绍",
        "说明",
        "当前系统状态",
        "系统状态",
        "帮我看",
        "问答",
    ),
    "nanofluidics.microfluidic_contact_angle_expert": (
        "接触角",
        "润湿",
        "液滴",
        "微流控",
        "微纳",
    ),
    "nanofluidics.nanofluidics_multimodel_expert": (
        "微纳",
        "微流体",
        "芯片流场",
        "气泡",
        "多模态分析",
    ),
}


VOICE_KEYWORD_FALLBACKS_CN = {
    "safety.chem_safety_expert": ("化学品", "危化品", "试剂", "药品", "标签", "试剂瓶", "药液"),
    "equipment_ocr_expert": ("ocr", "读数", "读一下", "识别设备", "仪表", "屏幕", "铭牌", "标签内容"),
    "lab_qa_expert": ("什么", "为什么", "如何", "介绍", "说明", "当前系统状态", "系统状态", "帮我看", "问答"),
    "nanofluidics.microfluidic_contact_angle_expert": ("接触角", "润湿", "液滴", "微流控", "微纳"),
    "nanofluidics.nanofluidics_multimodel_expert": ("微纳", "微流体", "芯片流场", "气泡", "多模态分析"),
}


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

    def _definition_for_expert(self, expert: BaseExpert):
        return get_expert_definition(expert.expert_code)

    def _iter_loaded_with_definition(self) -> Iterable[Tuple[BaseExpert, Any]]:
        for expert in self.experts.values():
            yield expert, self._definition_for_expert(expert)

    def _allowed_closed_loop_events(self, expert_code: str) -> set[str]:
        definition = get_expert_definition(expert_code)
        if definition is None:
            return set()
        return {str(item).strip() for item in getattr(definition, "event_names", ()) if str(item).strip()}

    def closed_loop_codes_for_event(self, event_name: str) -> List[str]:
        name = str(event_name or "").strip()
        if not name:
            return []

        matches: List[str] = []
        for expert, definition in self._iter_loaded_with_definition():
            if definition is None:
                continue
            allowed_names = self._allowed_closed_loop_events(expert.expert_code)
            if allowed_names and name in allowed_names:
                matches.append(expert.expert_code)
        return sorted(matches)

    @staticmethod
    def _normalize_voice_text(text: str) -> str:
        normalized = str(text or "").strip().lower().replace(" ", "")
        for filler in (
            "一下子",
            "一下",
            "帮我",
            "请帮我",
            "请",
            "看看",
            "识别一下",
            "读取一下",
            "识别",
            "读取",
            "帮忙",
        ):
            normalized = normalized.replace(filler, "")
        return normalized

    def _match_voice_keywords(self, definition: Any, command: str) -> bool:
        if definition is None:
            return False
        keywords = list(tuple(getattr(definition, "voice_keywords", ()) or ()))
        keywords.extend(VOICE_KEYWORD_FALLBACKS_CN.get(getattr(definition, "code", ""), ()))
        if not keywords:
            return False

        normalized_command = self._normalize_voice_text(command)
        lowered_command = str(command or "").strip().lower()
        for keyword in keywords:
            token = str(keyword).strip().lower()
            if not token:
                continue
            normalized_token = self._normalize_voice_text(token)
            if token in lowered_command or (normalized_token and normalized_token in normalized_command):
                return True
        return False

    def list_resident_stream_groups(self, media_type: str = "video") -> Dict[str, List[str]]:
        groups: Dict[str, List[str]] = defaultdict(list)
        for expert, definition in self._iter_loaded_with_definition():
            if definition is None:
                continue
            if getattr(definition, "trigger_mode", "resident") not in {"resident", "both"}:
                continue
            if media_type not in tuple(getattr(definition, "media_types", ()) or ()):
                continue
            groups[getattr(definition, "stream_group", "default")].append(expert.expert_code)
        return dict(groups)

    def get_aggregated_edge_policy(self) -> Dict[str, Any]:
        policies: List[Dict[str, Any]] = []
        for expert, definition in self._iter_loaded_with_definition():
            if definition is None:
                continue
            if getattr(definition, "trigger_mode", "resident") not in {"resident", "both"}:
                continue
            policy = expert.get_edge_policy()
            if not policy:
                continue

            raw_items: List[Dict[str, Any]] = []
            if isinstance(policy, list):
                raw_items = [item for item in policy if isinstance(item, dict)]
            elif isinstance(policy, dict):
                raw_items = [policy]

            allowed_names = self._allowed_closed_loop_events(expert.expert_code)
            for item in raw_items:
                event_name = str(item.get("event_name", "") or "").strip()
                if allowed_names and event_name and event_name not in allowed_names:
                    continue
                merged = dict(item)
                merged.setdefault("expert_code", expert.expert_code)
                merged.setdefault("policy_name", event_name or expert.expert_code)
                merged.setdefault("trigger_mode", getattr(definition, "trigger_mode", "resident"))
                merged.setdefault("stream_group", getattr(definition, "stream_group", "default"))
                merged.setdefault("default_speak_policy", getattr(definition, "default_speak_policy", "silent_log_only"))
                policies.append(merged)
        return {"event_policies": policies}

    def route_and_analyze(
        self,
        event_name: str,
        frame: Any,
        context: Dict[str, Any],
        *,
        allowed_expert_codes: Optional[Iterable[str]] = None,
        trigger_mode: Optional[str] = None,
    ) -> str:
        results: List[str] = []
        allowed_codes = {str(item).strip() for item in (allowed_expert_codes or []) if str(item).strip()}
        for expert, definition in self._iter_loaded_with_definition():
            if allowed_codes and expert.expert_code not in allowed_codes:
                continue
            if trigger_mode and definition is not None and getattr(definition, "trigger_mode", "resident") not in {trigger_mode, "both"}:
                continue
            if expert.match_event(event_name):
                try:
                    enriched = dict(context or {})
                    enriched.setdefault("event_name", event_name)
                    enriched.setdefault("expert", expert.expert_name)
                    enriched.update(self._build_knowledge_context(expert, event_name, enriched))
                    response = expert.analyze(frame, enriched)
                    if response:
                        results.append(self._postprocess_expert_response(expert, frame, enriched, response))
                except Exception as exc:
                    console_error(f"专家 [{expert.expert_name}] 分析异常: {exc}")
        return " ".join(results) if results else ""

    def _llm_interpreter_codes(self) -> set[str]:
        return {"safety.ppe_expert", "safety.chem_safety_expert"}

    def _should_use_llm_interpreter(self, expert: BaseExpert, context: Dict[str, Any]) -> bool:
        if expert.expert_code not in self._llm_interpreter_codes():
            return False
        if not (
            context.get("closed_loop_llm")
            or context.get("expert_code")
            or str(context.get("source") or "").strip() in {"pi_websocket", "virtual_pi_closed_loop", "gui_import_test"}
        ):
            return False
        if str(context.get("knowledge_context") or "").strip():
            return True
        if context.get("knowledge_structured_rows"):
            return True
        if context.get("knowledge_vector_hits"):
            return True
        return False

    def _interpreter_prompt(self, expert: BaseExpert, context: Dict[str, Any], raw_response: str) -> str:
        event_name = str(context.get("event_name") or context.get("event_desc") or "").strip()
        detected = str(context.get("detected_classes") or "").strip()
        policy_name = str(context.get("policy_name") or "").strip()
        facts = [f"专家初步结论：{raw_response.strip()}"]
        if event_name:
            facts.append(f"事件类型：{event_name}")
        if policy_name:
            facts.append(f"边缘策略：{policy_name}")
        if detected:
            facts.append(f"检测类别：{detected}")
        facts_text = "；".join(item for item in facts if item)
        if expert.expert_code == "safety.chem_safety_expert":
            return (
                "请基于危化品识别事实和实验室危化品知识库，输出一段简洁、专业、可播报的中文安全研判。"
                "优先说明危险源、缺失防护和立即处置动作，控制在90字内。"
                f"\n{facts_text}"
            )
        if expert.expert_code == "safety.ppe_expert":
            return (
                "请基于PPE检测事实和实验室着装规范知识库，输出一段简洁、专业、可播报的中文提醒。"
                "优先说明缺失防护、风险点和立即整改动作，控制在90字内。"
                f"\n{facts_text}"
            )
        return f"请基于以下事实和知识库内容，给出简洁专业的中文解释：\n{facts_text}"

    def _resolve_interpreter_model(self, context: Dict[str, Any]) -> str:
        model_name = str(context.get("model") or "").strip()
        if model_name:
            return model_name
        backend_name = str(get_config("ai_backend.type", "ollama") or "ollama").strip()
        try:
            from pc.core.ai_backend import default_model_for_backend
            return str(default_model_for_backend(backend_name) or "").strip()
        except Exception:
            return ""

    def _run_llm_interpreter(
        self,
        expert: BaseExpert,
        frame: Any,
        context: Dict[str, Any],
        raw_response: str,
    ) -> str:
        model_name = self._resolve_interpreter_model(context)
        if not model_name:
            return raw_response
        rag_context = str(context.get("knowledge_context") or "").strip()
        if not rag_context:
            rows = context.get("knowledge_structured_rows") or []
            rag_context = "\n".join(
                f"{row.get('name', '')}: {row.get('value', '')}" for row in rows if isinstance(row, dict)
            ).strip()
        if not rag_context:
            return raw_response
        prompt = self._interpreter_prompt(expert, context, raw_response)
        try:
            from pc.core.ai_backend import ask_assistant_with_rag
            interpreted = str(ask_assistant_with_rag(frame, prompt, rag_context, model_name) or "").strip()
            return interpreted or raw_response
        except Exception as exc:
            console_error(f"LLM 解释层失败 [{expert.expert_name}]: {exc}")
            return raw_response

    def _postprocess_expert_response(
        self,
        expert: BaseExpert,
        frame: Any,
        context: Dict[str, Any],
        raw_response: str,
    ) -> str:
        text = str(raw_response or "").strip()
        if not text:
            return ""
        if not self._should_use_llm_interpreter(expert, context):
            return text
        return self._run_llm_interpreter(expert, frame, context, text)

    def analyze_resident_frame(self, frame: Any, context: Dict[str, Any], *, media_type: str = "video") -> Dict[str, Any]:
        resident_groups = self.list_resident_stream_groups(media_type=media_type)
        group_results: Dict[str, str] = {}
        event_name = str((context or {}).get("event_name") or "").strip() or "综合安全巡检"

        for group_name, expert_codes in resident_groups.items():
            result = self.route_and_analyze(
                event_name,
                frame,
                dict(context or {}),
                allowed_expert_codes=expert_codes,
                trigger_mode="resident",
            )
            if result:
                group_results[group_name] = result

        return {
            "event_name": event_name,
            "stream_groups": resident_groups,
            "group_results": group_results,
            "text": " ".join(group_results[key] for key in sorted(group_results)).strip(),
        }

    def route_voice_command(
        self,
        command: str,
        frame: Any,
        context: Optional[Dict[str, Any]] = None,
        *,
        forced_expert_codes: Optional[Iterable[str]] = None,
    ) -> Dict[str, Any]:
        context = dict(context or {})
        context.setdefault("query", command)
        context.setdefault("question", command)

        forced_codes = {str(item).strip() for item in (forced_expert_codes or []) if str(item).strip()}
        matched_codes: List[str] = []
        group_results: Dict[str, str] = {}
        for expert, definition in self._iter_loaded_with_definition():
            if definition is None:
                continue
            if getattr(definition, "trigger_mode", "resident") not in {"voice", "both"}:
                continue
            if forced_codes:
                if expert.expert_code not in forced_codes:
                    continue
            elif not self._match_voice_keywords(definition, command):
                continue
            event_names = list(getattr(definition, "event_names", ()) or [])
            event_name = event_names[0] if event_names else (expert.supported_events()[0] if expert.supported_events() else f"VOICE::{expert.expert_code}")
            result = self.route_and_analyze(
                event_name,
                frame,
                context,
                allowed_expert_codes=[expert.expert_code],
                trigger_mode="voice",
            )
            if result:
                matched_codes.append(expert.expert_code)
                group_results[getattr(definition, "stream_group", expert.expert_code)] = result

        return {
            "matched_expert_codes": matched_codes,
            "group_results": group_results,
            "text": " ".join(group_results.values()).strip(),
        }

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
                    "trigger_mode": getattr(definition, "trigger_mode", "resident") if definition else "resident",
                    "stream_group": getattr(definition, "stream_group", "default") if definition else "default",
                    "voice_keywords": list(getattr(definition, "voice_keywords", ()) or ()) if definition else [],
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
                    "trigger_mode": definition.trigger_mode,
                    "stream_group": definition.stream_group,
                    "voice_keywords": list(definition.voice_keywords),
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

