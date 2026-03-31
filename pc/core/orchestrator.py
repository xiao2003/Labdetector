from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from pc.core.ai_backend import ask_assistant_with_rag, default_model_for_backend
from pc.core.expert_closed_loop import ExpertResult
from pc.core.expert_manager import expert_manager
from pc.core.monitoring_policy import should_speak_monitoring_result
from pc.core.orchestrator_model import infer_edge_plan, infer_voice_plan
from pc.core.orchestrator_runtime import get_runtime_status
from pc.knowledge_base.rag_engine import knowledge_manager


@dataclass
class OrchestratorResult:
    """统一编排后的标准结果。"""

    intent: str
    actions: List[Dict[str, Any]] = field(default_factory=list)
    text: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


def _build_rag_text(bundle: Dict[str, Any]) -> str:
    """把知识作用域检索结果整理成最小上下文。"""
    parts: List[str] = []
    context = str(bundle.get("context") or "").strip()
    if context:
        parts.append(context)

    rows = bundle.get("structured_rows") or []
    if rows:
        lines: List[str] = []
        for row in rows[:3]:
            scope_name = row.get("scope_title", row.get("scope", "知识库"))
            lines.append(f"[{scope_name}] {row.get('name', '')}: {str(row.get('value', ''))[:120]}")
        parts.append("结构化知识\n" + "\n".join(lines))

    return "\n\n".join(part for part in parts if str(part).strip())


def _resolve_knowledge_scope(expert_codes: Optional[List[str]] = None) -> str:
    """根据专家能力事实优先选择已就绪的专家知识域。"""
    fact_rows = {
        str(item.get("expert_code") or ""): item
        for item in expert_manager.list_expert_capability_facts()
        if str(item.get("expert_code") or "").strip()
    }
    for code in expert_codes or []:
        fact = fact_rows.get(str(code or "").strip())
        if not fact:
            continue
        if not bool(fact.get("loaded", False)):
            continue
        if not bool(fact.get("knowledge_required", False)):
            continue
        if not bool(fact.get("knowledge_ready", False)):
            continue
        scope_name = str(fact.get("knowledge_scope") or "").strip()
        if scope_name:
            return scope_name
    return "common"


def build_voice_rag_context(command: str, *, expert_codes: Optional[List[str]] = None) -> tuple[str, str]:
    """为语音问答构建与专家能力事实一致的知识上下文。"""
    scope_name = _resolve_knowledge_scope(expert_codes)
    try:
        bundle = knowledge_manager.build_scope_bundle(command, scope_name, top_k=3)
    except Exception:
        return "", scope_name
    return _build_rag_text(bundle), scope_name


APP_ACTION_RULES: Dict[str, Dict[str, Any]] = {
    "start_monitor": {
        "intent": "start_monitoring",
        "keywords": ("启动监控", "开始监控", "打开监控", "开始巡检", "开始检测"),
        "response": "好的，正在启动监控。",
    },
    "stop_monitor": {
        "intent": "stop_monitoring",
        "keywords": ("停止监控", "结束监控", "关闭监控", "停止巡检", "停止检测"),
        "response": "好的，正在停止监控。",
    },
    "run_self_check": {
        "intent": "query_system_status",
        "keywords": (
            "系统自检",
            "运行自检",
            "执行自检",
            "开始自检",
            "系统状态",
            "当前系统状态",
            "介绍当前系统状态",
            "查看系统状态",
            "汇报系统状态",
            "运行状态",
        ),
        "response": "好的，正在执行系统自检。",
    },
    "open_expert_center": {
        "intent": "open_view",
        "keywords": ("打开专家中心", "专家中心", "打开专家", "专家管理"),
        "response": "好的，正在打开专家中心。",
    },
    "open_knowledge_center": {
        "intent": "open_view",
        "keywords": ("打开知识中心", "知识中心", "打开知识库", "知识库管理"),
        "response": "好的，正在打开知识中心。",
    },
    "open_model_config": {
        "intent": "open_view",
        "keywords": ("打开模型配置", "模型配置", "模型服务", "打开模型服务"),
        "response": "好的，正在打开模型配置。",
    },
    "open_training_center": {
        "intent": "open_view",
        "keywords": ("打开训练中心", "训练中心", "打开训练台", "训练工作台"),
        "response": "好的，正在打开训练中心。",
    },
    "open_manual": {
        "intent": "open_view",
        "keywords": ("打开使用手册", "使用手册", "打开手册", "软件说明"),
        "response": "好的，正在打开使用手册。",
    },
    "open_about": {
        "intent": "open_view",
        "keywords": ("打开关于系统", "关于系统", "关于软件", "打开关于"),
        "response": "好的，正在打开关于系统。",
    },
    "toggle_sidebar": {
        "intent": "open_view",
        "keywords": ("切换侧栏", "折叠侧栏", "展开侧栏", "切换界面侧栏"),
        "response": "好的，正在切换界面侧栏。",
    },
    "shutdown_app": {
        "intent": "suppress_speech",
        "keywords": ("关闭软件", "退出软件", "关闭系统", "退出程序"),
        "response": "好的，正在关闭软件。",
    },
}


class Orchestrator:
    """PC 端统一编排入口。"""

    @staticmethod
    def _resolve_execution_model(model_name: str, context: Optional[Dict[str, Any]] = None) -> str:
        """解析当前应使用的执行层模型，避免隐式回退到过时默认值。"""
        candidate = str(model_name or "").strip()
        if candidate:
            return candidate
        route_context = dict(context or {})
        candidate = str(route_context.get("model") or "").strip()
        if candidate:
            return candidate
        backend_name = str(route_context.get("backend") or "").strip()
        if not backend_name:
            try:
                from pc.core.config import get_config

                backend_name = str(get_config("ai_backend.type", "ollama") or "ollama").strip()
            except Exception:
                backend_name = "ollama"
        return str(default_model_for_backend(backend_name) or "").strip()

    @staticmethod
    def runtime_status() -> Dict[str, Any]:
        status = get_runtime_status()
        return {
            "enabled": status.enabled,
            "ready": status.ready,
            "status": status.status,
            "planner_backend": status.planner_backend,
            "reason": status.reason,
            "runtime_path": status.runtime_path,
            "model_path": status.model_path,
        }

    @staticmethod
    def _normalize_text(text: str) -> str:
        normalized = str(text or "").strip().lower().replace(" ", "")
        for filler in ("一下子", "一下", "帮我", "请帮我", "请", "看看", "帮忙"):
            normalized = normalized.replace(filler, "")
        return normalized

    def _detect_app_action(self, text: str) -> Optional[Dict[str, Any]]:
        normalized = self._normalize_text(text)
        for action_name, rule in APP_ACTION_RULES.items():
            for keyword in rule.get("keywords", ()):
                if self._normalize_text(keyword) in normalized:
                    return {
                        "action_name": action_name,
                        "intent": str(rule.get("intent") or "").strip(),
                        "response": str(rule.get("response") or "").strip(),
                    }
        return None

    @staticmethod
    def _result_for_app_action(action_name: str, response_text: str, planner_backend: str) -> OrchestratorResult:
        return OrchestratorResult(
            intent="app_action",
            text=response_text,
            actions=[{"type": "app_action", "intent": action_name}],
            metadata={
                "matched_expert_codes": [],
                "has_frame": False,
                "rag_enabled": False,
                "planner_backend": planner_backend,
            },
        )

    def plan_voice_command(
        self,
        command: str,
        *,
        source: str,
        frame: Any,
        model_name: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> OrchestratorResult:
        text = str(command or "").strip()
        if not text:
            return OrchestratorResult(intent="empty")

        route_context = dict(context or {})
        route_context.setdefault("source", source)
        route_context.setdefault("query", text)
        route_context.setdefault("question", text)
        route_context.setdefault("event_name", "语音唤醒专家")
        route_context.setdefault("backend", str(route_context.get("backend") or ""))
        route_context.setdefault("model", self._resolve_execution_model(model_name, route_context))

        model_plan = infer_voice_plan(text, source=source, context=route_context)
        planner_backend = "embedded_model" if model_plan else "deterministic"
        model_intent = str(model_plan.get("intent", "") or "").strip() if model_plan else ""
        model_app_action = str(model_plan.get("app_intent", "") or "").strip() if model_plan else ""
        forced_codes = list(model_plan.get("expert_codes") or []) if model_plan else []
        need_knowledge = bool(model_plan.get("need_knowledge", False)) if model_plan else False

        if model_app_action and model_app_action in APP_ACTION_RULES:
            return self._result_for_app_action(
                model_app_action,
                str(model_plan.get("summary", "") or APP_ACTION_RULES[model_app_action]["response"]).strip(),
                planner_backend,
            )

        if not model_plan:
            detected_action = self._detect_app_action(text)
            if detected_action is not None:
                return self._result_for_app_action(
                    str(detected_action["action_name"]),
                    str(detected_action["response"]),
                    planner_backend,
                )

        expert_bundle = expert_manager.route_voice_command(
            text,
            frame,
            route_context,
            forced_expert_codes=forced_codes or None,
        )
        expert_answer = str(expert_bundle.get("text") or "").strip()
        if expert_answer:
            return OrchestratorResult(
                intent="call_expert_voice",
                text=expert_answer,
                actions=[
                    {
                        "type": "call_expert_voice",
                        "expert_codes": list(expert_bundle.get("matched_expert_codes") or []),
                    }
                ],
                metadata={
                    "matched_expert_codes": list(expert_bundle.get("matched_expert_codes") or []),
                    "has_frame": bool(frame is not None),
                    "rag_enabled": False,
                    "planner_backend": planner_backend,
                    "planner_summary": str(model_plan.get("summary", "") or "") if model_plan else "",
                },
            )

        if model_intent == "query_system_status":
            return OrchestratorResult(
                intent="query_system_status",
                text=str(model_plan.get("summary", "") or "当前系统状态查询请求已接收。").strip(),
                actions=[{"type": "query_system_status"}],
                metadata={
                    "matched_expert_codes": [],
                    "has_frame": bool(frame is not None),
                    "rag_enabled": False,
                    "planner_backend": planner_backend,
                },
            )

        knowledge_scope = "common"
        rag_context = ""
        if need_knowledge or not expert_answer:
            rag_context, knowledge_scope = build_voice_rag_context(
                text,
                expert_codes=list(expert_bundle.get("matched_expert_codes") or forced_codes),
            )
        answer = str(
            ask_assistant_with_rag(
                frame=frame,
                question=text,
                rag_context=rag_context,
                model_name=self._resolve_execution_model(model_name, route_context),
            )
            or ""
        ).strip()
        return OrchestratorResult(
            intent="answer_from_knowledge",
            text=answer,
            actions=[{"type": "answer_from_knowledge"}],
            metadata={
                "matched_expert_codes": [],
                "has_frame": bool(frame is not None),
                "rag_enabled": bool(rag_context.strip()),
                "knowledge_scope": knowledge_scope,
                "planner_backend": planner_backend,
                "planner_summary": str(model_plan.get("summary", "") or "") if model_plan else "",
            },
        )

    def plan_edge_event(
        self,
        *,
        pi_id: str,
        event: Any,
        selected_model: str,
        node_caps: Optional[Dict[str, Any]] = None,
    ) -> OrchestratorResult:
        allowed_codes: List[str] = []
        if getattr(event, "expert_code", None):
            allowed_codes = [str(event.expert_code).strip()]
        else:
            allowed_codes = expert_manager.closed_loop_codes_for_event(getattr(event, "event_name", ""))

        context = {
            "event_desc": getattr(event, "event_name", ""),
            "detected_classes": getattr(event, "detected_classes", ""),
            "metrics": getattr(event, "capture_metrics", {}),
            "expert_code": getattr(event, "expert_code", ""),
            "policy_name": getattr(event, "policy_name", ""),
            "policy_action": getattr(event, "policy_action", ""),
            "closed_loop_llm": True,
            "source": "pi_websocket",
            "model": selected_model,
            "pi_id": pi_id,
        }
        model_plan = infer_edge_plan(getattr(event, "event_name", ""), context=context)
        planner_backend = "embedded_model" if model_plan else "deterministic"
        if model_plan and model_plan.get("expert_codes"):
            allowed_codes = list(model_plan.get("expert_codes") or [])
        result_text = str(
            expert_manager.route_and_analyze(
                getattr(event, "event_name", ""),
                getattr(event, "frame", None),
                context,
                allowed_expert_codes=allowed_codes,
                trigger_mode=None if allowed_codes else "resident",
            )
            or ""
        ).strip()
        speak_policy = str(model_plan.get("speak_policy", "") or "").strip() if model_plan else ""
        speak_now = bool(
            (node_caps or {}).get("has_speaker", False) and (
                speak_policy == "speak_now"
                or (
                    not speak_policy
                    and should_speak_monitoring_result(getattr(event, "event_name", ""), result_text)
                )
            )
        )
        return OrchestratorResult(
            intent="call_expert_event",
            text=result_text,
            actions=[
                {
                    "type": "call_expert_event",
                    "expert_codes": allowed_codes,
                    "speak_policy": "speak_now" if speak_now else "silent_log_only",
                }
            ],
            metadata={
                "pi_id": pi_id,
                "event_id": getattr(event, "event_id", ""),
                "event_name": getattr(event, "event_name", ""),
                "speak_now": speak_now,
                "planner_backend": planner_backend,
                "planner_summary": str(model_plan.get("summary", "") or "") if model_plan else "",
                "timestamp": time.time(),
            },
        )

    def build_expert_result(self, orchestrated: OrchestratorResult) -> Optional[ExpertResult]:
        if not orchestrated.text.strip():
            return None
        return ExpertResult(
            event_id=str(orchestrated.metadata.get("event_id") or ""),
            text=orchestrated.text,
            severity="warning",
            speak=bool(orchestrated.metadata.get("speak_now", False)),
        )


orchestrator = Orchestrator()
