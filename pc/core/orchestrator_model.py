from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from pc.core.expert_manager import expert_manager
from pc.core.orchestrator_runtime import OrchestratorRuntimeError, invoke_orchestrator_model


def _expert_catalog_text() -> str:
    lines: List[str] = []
    for item in expert_manager.list_expert_capability_facts():
        voice_keywords = "、".join(item.get("voice_keywords", [])[:8]) if item.get("voice_keywords") else "无"
        event_names = "、".join(item.get("event_names", [])[:6]) if item.get("event_names") else "无"
        media_types = "、".join(item.get("media_types", [])[:4]) if item.get("media_types") else "无"
        lines.append(
            f"- code={item.get('expert_code')}; name={item.get('display_name')}; "
            f"trigger_mode={item.get('trigger_mode')}; loaded={item.get('loaded')}; "
            f"media_types={media_types}; voice_keywords={voice_keywords}; event_names={event_names}; "
            f"knowledge_required={item.get('knowledge_required')}; knowledge_scope={item.get('knowledge_scope')}; "
            f"knowledge_ready={item.get('knowledge_ready')}; priority={item.get('priority')}; "
            f"default_speak_policy={item.get('default_speak_policy')}"
        )
    return "\n".join(lines)


def _voice_prompt(command: str, source: str, context: Optional[Dict[str, Any]] = None) -> str:
    payload = {
        "type": "voice_command",
        "source": source,
        "command": str(command or "").strip(),
        "context": context or {},
    }
    return (
        "你是实验室多节点监控系统的固定管家层模型。"
        "你的唯一职责是把输入归一化为结构化任务计划。"
        "你只能在给定专家注册表里选择专家，禁止创造不存在的专家。"
        "请仅输出 JSON 对象，不要输出解释，不要输出 Markdown。\n\n"
        "允许的 intent:\n"
        "- answer_from_knowledge\n"
        "- call_expert_voice\n"
        "- query_system_status\n"
        "- start_monitoring\n"
        "- stop_monitoring\n"
        "- open_view\n"
        "- speak_text\n"
        "- suppress_speech\n\n"
        "JSON 模板:\n"
        "{"
        "\"intent\":\"call_expert_voice\","
        "\"expert_codes\":[\"expert.code\"],"
        "\"app_intent\":\"\","
        "\"need_knowledge\":false,"
        "\"speak_policy\":\"speak_now\","
        "\"summary\":\"给用户的简短回答\""
        "}\n\n"
        "专家注册表:\n"
        f"{_expert_catalog_text()}\n\n"
        "输入:\n"
        f"{json.dumps(payload, ensure_ascii=False)}"
    )


def _edge_prompt(event_name: str, context: Dict[str, Any]) -> str:
    payload = {
        "type": "edge_event",
        "event_name": str(event_name or "").strip(),
        "context": context,
    }
    return (
        "你是实验室多节点监控系统的固定管家层模型。"
        "请根据边缘事件和专家注册表，输出结构化任务计划。"
        "你只能在已注册专家范围内选择专家。"
        "请仅输出 JSON 对象，不要输出解释。\n\n"
        "允许的 intent:\n"
        "- call_expert_event\n"
        "- write_event_summary\n"
        "- suppress_speech\n\n"
        "JSON 模板:\n"
        "{"
        "\"intent\":\"call_expert_event\","
        "\"expert_codes\":[\"expert.code\"],"
        "\"need_knowledge\":false,"
        "\"speak_policy\":\"silent_log_only\","
        "\"summary\":\"事件摘要\""
        "}\n\n"
        "专家注册表:\n"
        f"{_expert_catalog_text()}\n\n"
        "输入:\n"
        f"{json.dumps(payload, ensure_ascii=False)}"
    )


def _normalize_plan(payload: Dict[str, Any]) -> Dict[str, Any]:
    intent = str(payload.get("intent", "") or "").strip()
    expert_codes_raw = payload.get("expert_codes") or []
    if isinstance(expert_codes_raw, str):
        expert_codes = [expert_codes_raw.strip()] if expert_codes_raw.strip() else []
    else:
        expert_codes = [str(item).strip() for item in expert_codes_raw if str(item).strip()]
    return {
        "intent": intent,
        "expert_codes": expert_codes,
        "app_intent": str(payload.get("app_intent", "") or "").strip(),
        "need_knowledge": bool(payload.get("need_knowledge", False)),
        "speak_policy": str(payload.get("speak_policy", "") or "").strip(),
        "summary": str(payload.get("summary", "") or "").strip(),
    }


def infer_voice_plan(command: str, *, source: str, context: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    try:
        payload = invoke_orchestrator_model(_voice_prompt(command, source, context))
    except OrchestratorRuntimeError:
        return None
    return _normalize_plan(payload)


def infer_edge_plan(event_name: str, *, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    try:
        payload = invoke_orchestrator_model(_edge_prompt(event_name, context))
    except OrchestratorRuntimeError:
        return None
    return _normalize_plan(payload)
