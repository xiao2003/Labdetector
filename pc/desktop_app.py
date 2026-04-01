#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Desktop visualization app for NeuroLab Hub."""

from __future__ import annotations

import ctypes
import json
import os
import queue
import re
import sys
import threading
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Any, Callable, Dict, List

import cv2
import numpy as np
from PIL import Image, ImageTk

from pc.app_identity import (
    APP_DESCRIPTION,
    APP_DISPLAY_NAME,
    APP_SHORT_TAGLINE,
    COMPANY_NAME,
    COPYRIGHT_TEXT,
    LEGAL_NOTICE,
    copyright_path,
    icon_path,
    logo_path,
    manual_path,
)
from pc.core.config import get_config, set_config
from pc.core.runtime_assets import DEFAULT_OLLAMA_MODELS
from pc.training.annotation_store import annotation_store
from pc.tools.version_manager import get_app_version

CUSTOM_MODEL_OPTION = "添加自定义模型..."
RECOMMENDED_MODEL_NAMES: Dict[str, List[str]] = {
    "ollama": list(DEFAULT_OLLAMA_MODELS),
}
VISIBLE_BACKENDS: List[str] = ["ollama", "qwen", "deepseek", "kimi", "local_adapter"]
CONFIG_BACKENDS: List[str] = ["qwen", "deepseek", "kimi"]
BACKEND_LABEL_OVERRIDES: Dict[str, str] = {
    "ollama": "Ollama",
    "local_adapter": "本地模型框架",
    "qwen": "通义千问（需在模型配置页面添加 API Key）",
    "deepseek": "DeepSeek（需在模型配置页面添加 API Key）",
    "kimi": "Kimi（需在模型配置页面添加 API Key）",
}
LOG_FILTER_OPTIONS: List[str] = ["全部", "告警", "调度", "系统"]


def _classify_log_entry(text: str, level: str, lowered: str) -> tuple[str, str]:
    """统一归类事件流条目，避免界面层出现多套分类规则。"""
    node_voice_in = re.match(r"^收到节点\s+(\d+)\s+语音指令[:：]\s*(.*)$", text)
    node_voice_out = re.match(r"^已回传节点\s+(\d+)\s+语音播报[:：]\s*(.*)$", text)
    node_event = re.match(r"^节点\s+\[(\d+)\]", text)
    if "任务进度" in text:
        summary = re.sub(r"\s+", " ", text).strip()
        return "任务进度", summary
    if "[autonomy]" in lowered:
        summary = re.sub(r"\s+", " ", re.sub(r"^\[autonomy\]\s*", "", text, flags=re.IGNORECASE)).strip()
        return "自治调度", summary
    if node_voice_in:
        summary = re.sub(r"\s+", " ", node_voice_in.group(2)).strip() or text
        return "节点语音", f"节点 {node_voice_in.group(1)} 上行：{summary}"
    if node_voice_out:
        summary = re.sub(r"\s+", " ", node_voice_out.group(2)).strip() or text
        return "节点播报", f"节点 {node_voice_out.group(1)} 下行：{summary}"
    if node_event:
        summary = re.sub(r"\s+", " ", text).strip()
        return "节点通信", f"节点 {node_event.group(1)}：{summary}"
    if "自检" in text:
        summary = re.sub(r"\s+", " ", text).strip()
        return "启动自检", summary
    if "知识库" in text or "作用域" in text:
        summary = re.sub(r"\s+", " ", text).strip()
        return "知识库", summary
    if "训练" in text or "工作区" in text or "标注" in text:
        summary = re.sub(r"\s+", " ", text).strip()
        return "训练", summary
    if "语音" in text or "唤醒" in text:
        summary = re.sub(r"\s+", " ", text).strip()
        return "语音交互", summary
    if "pi" in lowered or "websocket" in lowered:
        summary = re.sub(r"\s+", " ", text).strip()
        return "节点通信", summary
    if "模型" in text or "ollama" in lowered or "qwen" in lowered or "deepseek" in lowered:
        summary = re.sub(r"\s+", " ", text).strip()
        return "模型服务", summary
    summary = re.sub(r"\s+", " ", text).strip()
    return "系统", summary


def _present_log_category(category: str) -> str:
    """把内部分类收敛成界面可读口径，避免出现工程味标签。"""
    normalized = str(category or "").strip()
    if normalized == "任务进度":
        return "层状态"
    if normalized in {"节点语音", "节点播报", "节点通信"}:
        return "Pi 节点"
    if normalized in {"启动自检", "模型服务"}:
        return "系统"
    if normalized == "语音交互":
        return "语音"
    return normalized or "系统"


def _matches_log_filter(item: Dict[str, str], selected_filter: str) -> bool:
    """判断事件是否命中当前筛选器。"""
    if selected_filter == "全部":
        return True
    level = str(item.get("level") or "").upper()
    category = str(item.get("category") or "")
    if selected_filter == "告警":
        return level in {"WARN", "WARNING", "ERROR"}
    if selected_filter == "调度":
        return category in {"自治调度", "语音交互", "节点通信"}
    if selected_filter == "系统":
        return level not in {"WARN", "WARNING", "ERROR"} and category not in {"自治调度", "语音交互", "节点通信"}
    return True


def _present_orchestrator_status(status: str) -> str:
    """把管家层状态压缩成面向用户的三态文案。"""
    normalized = str(status or "").strip().lower()
    if normalized == "ready":
        return "系统已可用"
    if normalized == "download_failed":
        return "后台准备失败（已回退规则链）"
    return "后台准备中"


def _select_latest_priority_event(rows: List[Dict[str, str]]) -> Dict[str, str] | None:
    """从最近事件里提取一条需要常驻展示的高优事件摘要。"""
    for item in reversed(rows):
        level = str(item.get("level") or "").upper()
        summary = str(item.get("summary") or "")
        category = str(item.get("category") or "")
        if level in {"ERROR", "WARN", "WARNING"}:
            return item
        if any(keyword in summary for keyword in ("高危", "危险", "告警", "报警", "立即停止", "泄漏", "火焰", "烟雾")):
            return item
        if category in {"自治调度", "节点通信"} and "失败" in summary:
            return item
    return None


def _format_priority_event_card(item: Dict[str, str] | None) -> tuple[str, str]:
    """生成头部高优事件卡片文案。"""
    if item is None:
        return (
            "高优先级事项：当前无需要处理的事项",
            "",
        )
    summary = str(item.get("summary") or "暂无摘要")
    if len(summary) > 40:
        summary = summary[:37].rstrip() + "..."
    return (
        f"高优先级事项：{summary}",
        summary,
    )


def _format_kb_import_feedback(payload: Dict[str, Any], *, now: datetime | None = None) -> tuple[str, str]:
    """把知识导入结果整理成面向业务结果的反馈文案。"""
    current_time = now or datetime.now()
    scope_name = str(payload.get("scope") or "").strip() or "common"
    imported_count = int(payload.get("imported_count", 0) or 0)
    failed_count = int(payload.get("failed_count", 0) or 0)
    structured_count = int(payload.get("structured_records", 0) or 0)
    display_time = current_time.strftime("%Y-%m-%d %H:%M:%S")
    summary = f"最近一次导入：作用域 {scope_name} | 新增文档 {imported_count} | 最近一次导入时间 {display_time}"
    dialog_text = (
        f"作用域：{scope_name}\n"
        f"新增文档数：{imported_count}\n"
        f"失败条目数：{failed_count}\n"
        f"结构化记录数：{structured_count}\n"
        f"最近一次导入时间：{display_time}"
    )
    return summary, dialog_text


def _present_hero_message(status_message: str, orchestrator_status: str) -> str:
    """把系统状态文案收敛成首屏可读口径，避免旧工程状态词回流到 GUI。"""
    normalized_message = str(status_message or "").strip()
    if normalized_message in {"", "等待配置", "欢迎使用 NeuroLab Hub 主控制台"}:
        return _present_orchestrator_status(orchestrator_status)
    return normalized_message


def _task_card_payload(task: Dict[str, Any] | None, *, empty_title: str, empty_detail: str) -> Dict[str, Any]:
    """把运行任务统一整理成适合 GUI 卡片展示的结构。"""
    payload = dict(task or {})
    status = str(payload.get("status") or "").strip().lower()
    updated_ts = float(payload.get("updated_ts", 0.0) or 0.0)
    if status in {"success", "error"} and updated_ts and time.time() - updated_ts > 12.0:
        payload = {}
        status = ""
    if not payload:
        return {
            "active": False,
            "title": empty_title,
            "detail": empty_detail,
            "percent": 0.0,
            "status": "idle",
            "updated_at": "",
        }

    title = str(payload.get("task_name") or payload.get("title") or empty_title).strip() or empty_title
    detail = str(payload.get("detail") or payload.get("title") or empty_detail).strip() or empty_detail
    percent = max(0.0, min(100.0, float(payload.get("percent", 0.0) or 0.0)))
    return {
        "active": True,
        "title": title,
        "detail": detail,
        "percent": percent,
        "status": status or "running",
        "updated_at": str(payload.get("updated_at") or ""),
        "current": int(payload.get("current", 0) or 0),
        "total": int(payload.get("total", 0) or 0),
    }


def _format_task_progress_line(task: Dict[str, Any] | None, *, empty_title: str, empty_detail: str) -> tuple[str, str, float, str]:
    """生成运行任务卡片需要的标题、详情、进度和状态。"""
    payload = _task_card_payload(task, empty_title=empty_title, empty_detail=empty_detail)
    return (
        str(payload["title"]),
        str(payload["detail"]),
        float(payload["percent"]),
        str(payload["status"]),
    )


def _format_node_task_detail(node_id: str, task: Dict[str, Any] | None) -> str:
    """生成节点任务详情文本。"""
    payload = _task_card_payload(task, empty_title=f"节点 {node_id} 当前无任务", empty_detail="等待节点发起自检或安装。")
    detail_lines = [
        f"节点：{node_id}",
        f"状态：{payload['status']}",
        f"标题：{payload['title']}",
        f"详情：{payload['detail']}",
    ]
    if payload["updated_at"]:
        detail_lines.append(f"更新时间：{payload['updated_at']}")
    return "\n".join(detail_lines)


def _progress_bar_text(percent: float, *, width: int = 16) -> str:
    """生成单行进度条文本，供日志区直接展示。"""
    safe_percent = max(0.0, min(100.0, float(percent)))
    filled = int(round((safe_percent / 100.0) * width))
    filled = max(0, min(width, filled))
    return "[" + ("#" * filled) + ("-" * (width - filled)) + "]"


def _build_task_progress_log_item(
    *,
    scope_label: str,
    task: Dict[str, Any] | None,
    empty_title: str,
    empty_detail: str,
) -> Dict[str, str] | None:
    """把本机或节点任务进度转换成单行日志摘要。"""
    payload = _task_card_payload(task, empty_title=empty_title, empty_detail=empty_detail)
    if not bool(payload.get("active")):
        return None
    percent = float(payload.get("percent", 0.0) or 0.0)
    status = str(payload.get("status") or "running").strip().lower()
    level = "INFO"
    if status == "error":
        level = "ERROR"
    elif status == "success":
        level = "SUCCESS"
    summary = f"{scope_label} {str(payload.get('title') or '').strip()} {_progress_bar_text(percent)} {int(round(percent))}%"
    detail_text = str(payload.get("detail") or "").strip()
    if detail_text:
        summary = f"{summary} {detail_text}"
    updated_at = str(payload.get("updated_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    detail = (
        f"时间：{updated_at}\n"
        f"级别：{level}\n"
        f"模块：任务进度\n"
        f"内容：{summary}"
    )
    return {
        "key": f"task|{scope_label}|{str(payload.get('title') or '')}|{status}|{int(round(percent))}|{detail_text}",
        "time": updated_at,
        "level": level,
        "category": "任务进度",
        "summary": summary[:120] if len(summary) <= 120 else summary[:117].rstrip() + "...",
        "detail": detail,
    }


def _format_archive_record_label(row: Dict[str, Any]) -> str:
    """把实验档案记录编号转换成面向用户的简洁口径。"""
    opened_at = str(row.get("opened_at") or "").strip()
    if opened_at:
        return opened_at
    session_id = str(row.get("session_id") or "").strip()
    match = re.match(r"^(\d{8}_\d{6})", session_id)
    if match:
        return match.group(1)
    return session_id or "未命名记录"


class DesktopApp:
    def __init__(self) -> None:
        self._enable_dpi_awareness()
        self.app_version = get_app_version()
        self.runtime: Any | None = None
        self.root = tk.Tk()
        self._apply_windows_app_id()
        self.root.withdraw()
        self.skip_startup_splash = str(os.environ.get("NEUROLAB_SKIP_DESKTOP_SPLASH", "")).strip().lower() in {"1", "true", "yes", "on"}
        self.root.title(f"{APP_DISPLAY_NAME} v{self.app_version}")
        self.root.configure(bg="#0f1720")
        self.display_scale = self._detect_display_scale()
        self._apply_tk_scaling(self.display_scale)
        self.screen_width = self.root.winfo_screenwidth()
        self.screen_height = self.root.winfo_screenheight()
        self.window_width = 1600
        self.window_height = 1020
        self.left_panel_width = 400
        self.hero_wraplength = 860
        self.info_wraplength = 320
        self.summary_columns = 2
        self.stream_columns = 2
        self.stream_preview_width = 480
        self.stream_preview_height = 270
        self.gui_log_path = Path(__file__).resolve().parent / "log" / "gui_actions.log"
        self.gui_log_path.parent.mkdir(parents=True, exist_ok=True)
        self._configure_window_metrics()

        self.ui_queue: queue.Queue[tuple[str, str, Any]] = queue.Queue()
        self.photo_refs: Dict[str, ImageTk.PhotoImage] = {}
        self.stream_cards: Dict[str, Dict[str, Any]] = {}
        self.stream_frame_cache: Dict[str, Any] = {}
        self.stream_state_cache: Dict[str, Dict[str, Any]] = {}
        self.window_refs: List[tk.Toplevel] = []
        self.logo_image: ImageTk.PhotoImage | None = None
        self.splash_logo_image: ImageTk.PhotoImage | None = None
        self.splash: tk.Toplevel | None = None
        self.splash_progress_var = tk.DoubleVar(value=6.0)
        self.splash_step_var = tk.StringVar(value="步骤 1/3：初始化运行环境")
        self.splash_detail_var = tk.StringVar(value="正在检查运行环境、依赖组件和本地资源，请稍候")
        self.voice_test_prompted = False
        self.backend_map: Dict[str, str] = {}
        self.backend_reverse: Dict[str, str] = {}
        self.mode_map: Dict[str, str] = {}
        self.mode_reverse: Dict[str, str] = {}
        self.model_catalog: Dict[str, List[str]] = {}
        self.knowledge_catalog: List[Dict[str, Any]] = []
        self.kb_scope_map: Dict[str, str] = {}
        self.kb_scope_reverse: Dict[str, str] = {}
        self.kb_window: tk.Toplevel | None = None
        self.kb_tree: ttk.Treeview | None = None
        self.kb_scope_combo: ttk.Combobox | None = None
        self.kb_detail_text: tk.Text | None = None
        self.manual_window: tk.Toplevel | None = None
        self.about_window: tk.Toplevel | None = None
        self.copyright_window: tk.Toplevel | None = None
        self.expert_catalog: List[Dict[str, Any]] = []
        self.expert_window: tk.Toplevel | None = None
        self.expert_tree: ttk.Treeview | None = None
        self.expert_detail_text: tk.Text | None = None
        self.expert_status_var = tk.StringVar(value="等待加载专家模型")
        self.cloud_backend_catalog: List[Dict[str, Any]] = []
        self.archive_catalog: List[Dict[str, Any]] = []
        self.training_overview: Dict[str, Any] = {}
        self.archive_window: tk.Toplevel | None = None
        self.archive_tree: ttk.Treeview | None = None
        self.archive_detail_text: tk.Text | None = None
        self.archive_status_var = tk.StringVar(value="等待加载实验档案")
        self.training_window: tk.Toplevel | None = None
        self.training_notebook: ttk.Notebook | None = None
        self.main_notebook: ttk.Notebook | None = None
        self.overview_tab: ttk.Frame | None = None
        self.kb_tab: ttk.Frame | None = None
        self.expert_tab: ttk.Frame | None = None
        self.model_tab: ttk.Frame | None = None
        self.training_tab: ttk.Frame | None = None
        self.archive_tab: ttk.Frame | None = None
        self.pc_layer_tree: ttk.Treeview | None = None
        self.pi_layer_tree: ttk.Treeview | None = None
        self.pc_layer_cards_frame: ttk.Frame | None = None
        self.pi_layer_cards_frame: ttk.Frame | None = None
        self.pc_dashboard_panel: ttk.Frame | None = None
        self.pi_dashboard_panel: ttk.Frame | None = None
        self.dashboard_priority_label: ttk.Label | None = None
        self.training_detail_text: tk.Text | None = None
        self.training_workspace_entry: ttk.Entry | None = None
        self.training_base_model_entry: ttk.Entry | None = None
        self.training_pi_weights_entry: ttk.Entry | None = None
        self.training_annotation_canvas: tk.Canvas | None = None
        self.training_annotation_tree: ttk.Treeview | None = None
        self.training_annotation_box_tree: ttk.Treeview | None = None
        self.training_annotation_class_entry: ttk.Entry | None = None
        self.training_annotation_photo: ImageTk.PhotoImage | None = None
        self.training_annotation_status_var = tk.StringVar(value="等待导入训练图片并开始标注")
        self.training_annotation_workspace_dir = ""
        self.training_annotation_workspace_pending = False
        self.training_annotation_items: List[Dict[str, Any]] = []
        self.training_annotation_current_item: Dict[str, Any] = {}
        self.training_annotation_boxes: List[Dict[str, Any]] = []
        self.training_annotation_scale = 1.0
        self.training_annotation_offset = (0, 0)
        self.training_annotation_image_size = (0, 0)
        self.training_annotation_drag_start: tuple[int, int] | None = None
        self.training_annotation_preview_rect: int | None = None
        self.training_status_var = tk.StringVar(value="等待导入训练数据")
        self.cloud_window: tk.Toplevel | None = None
        self.cloud_provider_combo: ttk.Combobox | None = None
        self.cloud_provider_map: Dict[str, str] = {}
        self.cloud_provider_reverse: Dict[str, str] = {}
        self.cloud_api_key_entry: ttk.Entry | None = None
        self.cloud_base_url_entry: ttk.Entry | None = None
        self.cloud_model_entry: ttk.Entry | None = None
        self.cloud_model_alias_entry: ttk.Entry | None = None
        self.cloud_status_var = tk.StringVar(value="等待配置模型服务")
        self.stream_viewer_window: tk.Toplevel | None = None
        self.stream_viewer_label: tk.Label | None = None
        self.stream_viewer_title_var = tk.StringVar(value="")
        self.stream_viewer_meta_var = tk.StringVar(value="")
        self.stream_viewer_photo: ImageTk.PhotoImage | None = None
        self.stream_viewer_stream_id: str | None = None
        self.shell_frame: ttk.Frame | None = None
        self.left_panel: ttk.Frame | None = None
        self.left_canvas: tk.Canvas | None = None
        self.left_inner: ttk.Frame | None = None
        self.left_window: int | None = None
        self.wall_canvas: tk.Canvas | None = None
        self.wall_inner: ttk.Frame | None = None
        self.wall_window: int | None = None
        self.log_tree: ttk.Treeview | None = None
        self.log_canvas: tk.Canvas | None = None
        self.log_content: ttk.Frame | None = None
        self.log_content_window: int | None = None
        self.log_overall_scroll: ttk.Scrollbar | None = None
        self.local_task_status_label: ttk.Label | None = None
        self.local_task_empty_hint: ttk.Label | None = None
        self.node_task_title_label: ttk.Label | None = None
        self.node_task_cards: Dict[str, Dict[str, Any]] = {}
        self.check_tree: ttk.Treeview | None = None
        self.node_logs_title: ttk.Label | None = None
        self.main_log_panel: ttk.Frame | None = None
        self.log_detail_panel: ttk.Frame | None = None
        self.log_detail_text: tk.Text | None = None
        self.log_status_var = tk.StringVar(value="等待系统事件")
        self.log_filter_var = tk.StringVar(value=LOG_FILTER_OPTIONS[0])
        self.priority_event_title_var = tk.StringVar(value="高优先级事项：当前无需要处理的事项")
        self.priority_event_detail_var = tk.StringVar(value="")
        self.layer_issue_title_var = tk.StringVar(value="当前未发现需要处理的异常")
        self.layer_issue_detail_var = tk.StringVar(value="首次启动后，系统会自动补全缺失项并再次自检。")
        self.layer_issue_action_var = tk.StringVar(value="暂无修复动作")
        self.task_progress_rows: List[Dict[str, str]] = []
        self.log_row_keys: List[str] = []
        self.log_rows: List[Dict[str, str]] = []
        self.log_filter_combo: ttk.Combobox | None = None
        self.node_log_panel: ttk.Frame | None = None
        self.node_log_canvas: tk.Canvas | None = None
        self.node_log_inner: ttk.Frame | None = None
        self.node_log_window: int | None = None
        self.node_logs_container: ttk.Frame | None = None
        self.node_log_empty_label: ttk.Label | None = None
        self.node_log_cards: Dict[str, ttk.Treeview] = {}
        self.node_log_cache: Dict[str, List[str]] = {}
        self.layer_issue_button: ttk.Button | None = None
        self.layer_issue_card: ttk.Frame | None = None
        self.current_layer_issue: Dict[str, Any] = {}
        self.main_splitter: tk.PanedWindow | None = None
        self.main_splitter_user_resized = False
        self.main_splitter_mode = "idle"
        self.model_delete_button: ttk.Button | None = None
        self.session_badge: tk.Label | None = None
        self.hero_message_label: ttk.Label | None = None
        self.info_description_label: ttk.Label | None = None
        self.info_copyright_label: ttk.Label | None = None
        self.priority_event_detail_label: ttk.Label | None = None
        self.resize_after_id: str | None = None
        self.window_state_after_id: str | None = None
        self.stream_refresh_after_id: str | None = None
        self.tooltip_window: tk.Toplevel | None = None
        self.tooltip_after_id: str | None = None
        self.demo_restore_geometry: str | None = None
        self.demo_restore_state: str = "normal"
        self.demo_restore_collapsed: bool = False
        self.startup_self_check_started = False
        self.orchestrator_prepare_started = False
        self.voice_local_handler_started = False
        self.voice_local_handler_ready = False
        self.is_closing = False
        self.scroll_routes: Dict[str, Dict[str, Any]] = {}
        self.hidden_demo_enabled = bool(get_config("shadow_demo.enabled", False))
        self.current_state: Dict[str, Any] = {
            "summary": {},
            "session": {},
            "streams": [],
            "self_check": [],
            "logs": [],
            "tasks": {},
        }

        self.backend_var = tk.StringVar()
        self.model_var = tk.StringVar()
        self.custom_model_var = tk.StringVar()
        self.custom_model_registry: Dict[str, List[Dict[str, str]]] = {}
        self.mode_var = tk.StringVar(value="camera")
        self.expected_nodes_var = tk.StringVar(value="1")
        self.hero_var = tk.StringVar(value="正在启动 NeuroLab Hub")
        self.session_var = tk.StringVar(value="待机")
        self.brand_var = tk.StringVar(value=f"{COMPANY_NAME} 版本 v{self.app_version}")
        self.footer_var = tk.StringVar(value=COPYRIGHT_TEXT)
        self.splash_message_var = tk.StringVar(value="正在初始化核心服务并准备主界面")
        self.kb_status_var = tk.StringVar(value="等待导入知识库")
        self.kb_reset_var = tk.BooleanVar(value=False)
        self.kb_structured_var = tk.BooleanVar(value=True)
        self.left_collapsed_var = tk.BooleanVar(value=False)
        self.demo_mode_var = tk.BooleanVar(value=False)
        self.project_entry: ttk.Entry | None = None
        self.experiment_entry: ttk.Entry | None = None
        self.operator_entry: ttk.Entry | None = None
        self.tags_entry: ttk.Entry | None = None

        self.summary_vars = {
            "mode": tk.StringVar(value="-"),
            "online": tk.StringVar(value="0"),
            "offline": tk.StringVar(value="0"),
            "voice": tk.StringVar(value="OFF"),
            "orchestrator": tk.StringVar(value="后台准备中"),
            "planner": tk.StringVar(value="规则链"),
        }
        self.dashboard_tab_map: Dict[str, str] = {
            "overview": "总览",
            "knowledge": "知识中心",
            "expert": "专家中心",
            "model": "模型配置",
            "training": "训练中心",
            "archive": "档案中心",
        }
        self.hero_var.set("正在启动 NeuroLab Hub")
        self.session_var.set("待机")
        self.brand_var.set(f"{COMPANY_NAME} 版本 v{self.app_version}")
        self.splash_message_var.set("正在初始化核心服务并准备主界面")
        self.kb_status_var.set("等待导入知识库")

        self._build_style()
        self._apply_branding()
        self._build_menu()
        self._build_layout()
        self._restore_window_state()
        if not self.skip_startup_splash:
            self._show_startup_splash()
        self._bind_events()
        self._load_bootstrap()

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(250, self._process_queue)
        self.root.after(120, self._refresh_streams_tick)
        self.root.after(1200, self._refresh_state_tick)

    def _build_style(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure("Root.TFrame", background="#0f1720")
        style.configure("Panel.TFrame", background="#182330")
        style.configure("SoftPanel.TFrame", background="#223143")
        style.configure("Card.TFrame", background="#243548")
        style.configure("Header.TLabel", background="#182330", foreground="#f5f7fb", font=("Microsoft YaHei UI", 25, "bold"))
        style.configure("Body.TLabel", background="#182330", foreground="#d7e0ea", font=("Microsoft YaHei UI", 10))
        style.configure("Brand.TLabel", background="#182330", foreground="#78e6ff", font=("Microsoft YaHei UI", 10, "bold"))
        style.configure("PanelTitle.TLabel", background="#182330", foreground="#f5f7fb", font=("Microsoft YaHei UI", 13, "bold"))
        style.configure("MetricValue.TLabel", background="#243548", foreground="#ffffff", font=("Bahnschrift", 20, "bold"))
        style.configure("MetricLabel.TLabel", background="#243548", foreground="#c3d0dc", font=("Microsoft YaHei UI", 9))
        style.configure("CardBody.TLabel", background="#243548", foreground="#d7e0ea", font=("Microsoft YaHei UI", 10))
        style.configure("CardFoot.TLabel", background="#243548", foreground="#9fb6c9", font=("Microsoft YaHei UI", 10))
        style.configure("Foot.TLabel", background="#182330", foreground="#9fb6c9", font=("Microsoft YaHei UI", 10))
        style.configure("SplashTitle.TLabel", background="#0b1e2d", foreground="#ffffff", font=("Microsoft YaHei UI", 28, "bold"))
        style.configure("SplashBody.TLabel", background="#182330", foreground="#d6e6f2", font=("Microsoft YaHei UI", 11))
        style.configure("SplashMeta.TLabel", background="#182330", foreground="#d6e6f2", font=("Microsoft YaHei UI", 10))
        style.configure("SplashStatus.TLabel", background="#182330", foreground="#f3f7fb", font=("Microsoft YaHei UI", 11, "bold"))
        style.configure("SplashHint.TLabel", background="#182330", foreground="#9fb6c9", font=("Microsoft YaHei UI", 9))
        style.configure("TButton", font=("Microsoft YaHei UI", 10), padding=(self._scaled(10), self._scaled(8)))
        style.configure("Accent.TButton", font=("Microsoft YaHei UI", 10, "bold"), padding=(self._scaled(10), self._scaled(8)))
        style.configure("Nav.TButton", font=("Microsoft YaHei UI", 11, "bold"), padding=(self._scaled(12), self._scaled(8)))
        style.configure("TCombobox", padding=self._scaled(6))
        try:
            style.layout("Dashboard.TNotebook.Tab", [])
        except Exception:
            pass
        style.configure("Dashboard.TNotebook", background="#0f1720", borderwidth=0, tabmargins=(0, 0, 0, 0))
        style.configure(
            "Treeview",
            rowheight=self._scaled(38),
            font=("Microsoft YaHei UI", 10),
            fieldbackground="#223143",
            background="#223143",
            foreground="#f5f7fb",
        )
        style.configure("Treeview.Heading", font=("Microsoft YaHei UI", 10, "bold"))

    @staticmethod
    def _enable_dpi_awareness() -> None:
        if sys.platform != "win32":
            return
        try:
            ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
            return
        except Exception:
            pass
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
            return
        except Exception:
            pass
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

    @staticmethod
    def _apply_windows_app_id() -> None:
        if sys.platform != "win32":
            return
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("NeuroLab.Hub.Desktop")
        except Exception:
            pass

    def _detect_display_scale(self) -> float:
        try:
            dpi = float(self.root.winfo_fpixels("1i"))
        except Exception:
            dpi = 96.0
        return max(1.0, min(dpi / 96.0, 2.5))

    def _apply_tk_scaling(self, scale: float) -> None:
        try:
            self.root.tk.call("tk", "scaling", max(1.3333, min((scale * 96.0) / 72.0, 3.3333)))
        except Exception:
            pass

    def _detect_window_scale(self) -> float:
        if sys.platform != "win32":
            return self._detect_display_scale()
        try:
            hwnd = int(self.root.winfo_id())
        except Exception:
            hwnd = 0
        if hwnd:
            try:
                dpi = float(ctypes.windll.user32.GetDpiForWindow(hwnd))
                if dpi > 0:
                    return max(1.0, min(dpi / 96.0, 2.5))
            except Exception:
                pass
            try:
                monitor = ctypes.windll.user32.MonitorFromWindow(hwnd, 2)
                dpi_x = ctypes.c_uint()
                dpi_y = ctypes.c_uint()
                ctypes.windll.shcore.GetDpiForMonitor(monitor, 0, ctypes.byref(dpi_x), ctypes.byref(dpi_y))
                if dpi_x.value:
                    return max(1.0, min(float(dpi_x.value) / 96.0, 2.5))
            except Exception:
                pass
        return self._detect_display_scale()

    def _scaled(self, value: int) -> int:
        return max(1, int(round(value * self.display_scale)))

    def _configure_window_metrics(self) -> None:
        screen_w = max(self.screen_width, 1280)
        screen_h = max(self.screen_height, 860)
        width = min(max(int(screen_w * 0.84), 1360), max(screen_w - self._scaled(80), 1200))
        height = min(max(int(screen_h * 0.88), 900), max(screen_h - self._scaled(80), 860))
        self.window_width = width
        self.window_height = height
        self.left_panel_width = self._compute_left_panel_width(width)
        self.hero_wraplength = max(480, min(width - self.left_panel_width - 280, 1120))
        self.info_wraplength = max(260, self.left_panel_width - 72)
        min_width = max(1180, min(width - self._scaled(200), 1440))
        min_height = max(820, min(height - self._scaled(160), 980))
        offset_x = max(20, int((screen_w - width) / 2))
        offset_y = max(20, int((screen_h - height) / 2))
        self.root.geometry(f"{width}x{height}+{offset_x}+{offset_y}")
        self.root.minsize(min_width, min_height)

    def _compute_left_panel_width(self, width: int) -> int:
        preferred = int(width * 0.24)
        lower = 340 if self.display_scale < 1.25 else 360
        upper = min(520, int(width * 0.3))
        return max(lower, min(preferred, upper))

    def _apply_branding(self) -> None:
        try:
            ico = icon_path()
            if ico.exists():
                self.root.iconbitmap(default=str(ico))
        except Exception:
            pass

        try:
            logo_file = logo_path()
            if logo_file.exists():
                image = Image.open(logo_file).resize((96, 96), Image.Resampling.LANCZOS)
                self.logo_image = ImageTk.PhotoImage(image)
                self.root.iconphoto(True, self.logo_image)
        except Exception:
            self.logo_image = None

    def _apply_close_only_window_style(self, window: tk.Toplevel) -> None:
        if sys.platform != "win32":
            return
        try:
            hwnd = int(window.winfo_id())
        except Exception:
            return
        if not hwnd:
            return
        try:
            style = ctypes.windll.user32.GetWindowLongW(hwnd, -16)
            ws_minimizebox = 0x00020000
            ws_maximizebox = 0x00010000
            style &= ~ws_minimizebox
            style &= ~ws_maximizebox
            ctypes.windll.user32.SetWindowLongW(hwnd, -16, style)
            ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0027)
        except Exception:
            pass


    def _build_layout(self) -> None:
        shell = ttk.Frame(self.root, style="Root.TFrame", padding=14)
        shell.pack(fill="both", expand=True)
        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(2, weight=1)
        self.shell_frame = shell

        hero = ttk.Frame(shell, style="Panel.TFrame", padding=14)
        hero.grid(row=0, column=0, sticky="nsew", pady=(0, 12))
        hero.columnconfigure(0, weight=1)
        hero.columnconfigure(1, weight=0)

        hero_left = ttk.Frame(hero, style="Panel.TFrame")
        hero_left.grid(row=0, column=0, sticky="nsew")
        hero_meta = ttk.Frame(hero_left, style="Panel.TFrame")
        hero_meta.pack(anchor="w", fill="x")
        hero_logo = self._load_logo_image((48, 48))
        if hero_logo is not None:
            self.logo_image = hero_logo
            tk.Label(hero_meta, image=self.logo_image, bg="#182330").pack(side="left", padx=(0, 12))
        ttk.Label(hero_meta, text=APP_DISPLAY_NAME, style="Header.TLabel").pack(side="left")
        ttk.Label(hero_meta, text=f"v{self.app_version}", style="Foot.TLabel").pack(
            side="left",
            padx=(12, 0),
            pady=(8, 0),
        )
        hero_nav = ttk.Frame(hero, style="Panel.TFrame")
        hero_nav.grid(row=0, column=1, sticky="ne", padx=(16, 0))
        hero_nav_buttons = ttk.Frame(hero_nav, style="Panel.TFrame")
        hero_nav_buttons.grid(row=0, column=0, sticky="e")
        self._grid_action_bar(
            hero_nav_buttons,
            [
                ttk.Button(hero_nav_buttons, text="总览", style="Nav.TButton", command=lambda: self._select_dashboard_tab("overview")),
                ttk.Button(hero_nav_buttons, text="专家中心", style="Nav.TButton", command=lambda: self._select_dashboard_tab("expert")),
                ttk.Button(hero_nav_buttons, text="知识中心", style="Nav.TButton", command=lambda: self._select_dashboard_tab("knowledge")),
                ttk.Button(hero_nav_buttons, text="模型配置", style="Nav.TButton", command=lambda: self._select_dashboard_tab("cloud")),
                ttk.Button(hero_nav_buttons, text="训练中心", style="Nav.TButton", command=lambda: self._select_dashboard_tab("training")),
                ttk.Button(hero_nav_buttons, text="档案中心", style="Nav.TButton", command=lambda: self._select_dashboard_tab("archive")),
            ],
            columns=6,
        )
        self.session_badge = tk.Label(
            hero_nav,
            textvariable=self.session_var,
            bg="#f6c344",
            fg="#0f1720",
            font=("Microsoft YaHei UI", 10, "bold"),
            padx=10,
            pady=6,
        )
        self.session_badge.grid(row=0, column=1, sticky="e", padx=(12, 0))
        self.hero_message_label = None

        notebook = ttk.Notebook(shell, style="Dashboard.TNotebook")
        notebook.grid(row=1, column=0, sticky="nsew")
        self.main_notebook = notebook

        self.overview_tab = ttk.Frame(notebook, style="Root.TFrame", padding=14)
        self.kb_tab = ttk.Frame(notebook, style="Root.TFrame", padding=14)
        self.expert_tab = ttk.Frame(notebook, style="Root.TFrame", padding=14)
        self.model_tab = ttk.Frame(notebook, style="Root.TFrame", padding=14)
        self.training_tab = ttk.Frame(notebook, style="Root.TFrame", padding=14)
        self.archive_tab = ttk.Frame(notebook, style="Root.TFrame", padding=14)

        notebook.add(self.overview_tab, text="总览")
        notebook.add(self.expert_tab, text="专家中心")
        notebook.add(self.kb_tab, text="知识中心")
        notebook.add(self.model_tab, text="模型配置")
        notebook.add(self.training_tab, text="训练中心")
        notebook.add(self.archive_tab, text="档案中心")

        self._build_overview_dashboard(self.overview_tab)
        self._build_embedded_knowledge_panel(self.kb_tab)
        self._build_embedded_expert_panel(self.expert_tab)
        self._build_embedded_cloud_panel(self.model_tab)
        self._build_embedded_training_panel(self.training_tab)
        self._build_embedded_archive_panel(self.archive_tab)

        hidden_host = ttk.Frame(shell, style="Root.TFrame")
        self.main_log_panel = hidden_host
        self.wall_canvas = tk.Canvas(hidden_host, bg="#182330", highlightthickness=0, width=4, height=4)
        self.wall_inner = ttk.Frame(self.wall_canvas, style="Root.TFrame")
        self.wall_window = self.wall_canvas.create_window((0, 0), window=self.wall_inner, anchor="nw")

        footer = ttk.Frame(shell, style="Panel.TFrame", padding=(20, 10))
        footer.grid(row=2, column=0, sticky="ew", pady=(16, 0))
        footer.columnconfigure(0, weight=1)
        ttk.Label(footer, textvariable=self.footer_var, style="Foot.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(footer, text=f"{COMPANY_NAME} | v{self.app_version}", style="Foot.TLabel").grid(row=0, column=1, sticky="e")
        if self.check_tree is not None:
            self._register_scroll_target(self.check_tree, self.check_tree)

    def _build_overview_dashboard(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=3)
        parent.columnconfigure(1, weight=2)
        parent.rowconfigure(0, weight=1)

        self.pc_dashboard_panel = ttk.Frame(parent, style="Panel.TFrame")
        self.pc_dashboard_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        self.pc_dashboard_panel.columnconfigure(0, weight=1)
        self.pc_dashboard_panel.rowconfigure(1, weight=1)

        summary_panel = ttk.Frame(self.pc_dashboard_panel, style="SoftPanel.TFrame", padding=16)
        summary_panel.grid(row=0, column=0, sticky="nsew")
        summary_panel.columnconfigure(0, weight=1)
        summary_panel.rowconfigure(2, weight=1)
        summary_header = ttk.Frame(summary_panel, style="SoftPanel.TFrame")
        summary_header.grid(row=0, column=0, sticky="ew")
        summary_header.columnconfigure(0, weight=1)
        ttk.Label(summary_header, text="总仪表盘", style="PanelTitle.TLabel").grid(row=0, column=0, sticky="w")
        overview_actions = ttk.Frame(summary_header, style="SoftPanel.TFrame")
        overview_actions.grid(row=0, column=1, sticky="e")
        self._grid_action_bar(
            overview_actions,
            [
                ttk.Button(overview_actions, text="刷新模型", command=self._refresh_models),
                ttk.Button(overview_actions, text="系统自检", command=self._run_self_check),
                ttk.Button(overview_actions, text="启动监控", style="Accent.TButton", command=self._start_session),
                ttk.Button(overview_actions, text="停止监控", command=self._stop_session),
            ],
            columns=4,
        )
        self.layer_issue_card = ttk.Frame(summary_panel, style="Card.TFrame", padding=12)
        self.layer_issue_card.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        self.layer_issue_card.columnconfigure(0, weight=1)
        ttk.Label(self.layer_issue_card, textvariable=self.layer_issue_title_var, style="PanelTitle.TLabel").grid(row=0, column=0, sticky="w")
        layer_issue_detail = ttk.Label(
            self.layer_issue_card,
            textvariable=self.layer_issue_detail_var,
            style="Body.TLabel",
            justify="left",
        )
        layer_issue_detail.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        self._register_adaptive_wrap_label(layer_issue_detail, self.layer_issue_card, padding=24, min_width=280, max_width=760)
        self.layer_issue_button = ttk.Button(self.layer_issue_card, textvariable=self.layer_issue_action_var, command=self._repair_selected_layer_issue)
        self.layer_issue_button.grid(row=0, column=1, rowspan=2, sticky="e", padx=(12, 0))
        self.summary_frame = None
        self.pc_layer_cards_frame = ttk.Frame(summary_panel, style="SoftPanel.TFrame")
        self.pc_layer_cards_frame.grid(row=2, column=0, sticky="nsew", pady=(12, 0))
        for column in range(3):
            self.pc_layer_cards_frame.columnconfigure(column, weight=1)
        self.pi_layer_cards_frame = None

        log_panel = ttk.Frame(self.pc_dashboard_panel, style="Panel.TFrame")
        log_panel.grid(row=1, column=0, sticky="nsew", pady=(14, 0))
        log_panel.columnconfigure(0, weight=1)
        log_panel.rowconfigure(1, weight=1)

        log_header = ttk.Frame(log_panel, style="SoftPanel.TFrame", padding=16)
        log_header.grid(row=0, column=0, sticky="ew")
        log_header.columnconfigure(0, weight=1)
        self.dashboard_priority_label = ttk.Label(log_header, textvariable=self.priority_event_title_var, style="PanelTitle.TLabel", justify="left")
        self.dashboard_priority_label.grid(row=0, column=0, sticky="ew")
        self._register_adaptive_wrap_label(self.dashboard_priority_label, log_header, padding=24, min_width=260, max_width=520)

        log_body = ttk.Frame(log_panel, style="SoftPanel.TFrame", padding=16)
        log_body.grid(row=1, column=0, sticky="nsew", pady=(14, 0))
        log_body.columnconfigure(0, weight=1)
        log_body.rowconfigure(0, weight=1)
        self.log_tree = ttk.Treeview(log_body, columns=("time", "level", "category", "summary"), show="headings")
        self.log_tree.heading("time", text="时间")
        self.log_tree.heading("level", text="级别")
        self.log_tree.heading("category", text="层/节点")
        self.log_tree.heading("summary", text="事项")
        self.log_tree.column("time", width=142, anchor="w")
        self.log_tree.column("level", width=90, anchor="center")
        self.log_tree.column("category", width=110, anchor="center")
        self.log_tree.column("summary", width=460, anchor="w")
        self.log_tree.grid(row=0, column=0, sticky="nsew")
        log_scroll = ttk.Scrollbar(log_body, orient="vertical", command=self.log_tree.yview)
        log_scroll.grid(row=0, column=1, sticky="ns")
        self.log_tree.configure(yscrollcommand=log_scroll.set)
        self.log_tree.tag_configure("INFO", foreground="#dbe6f2")
        self.log_tree.tag_configure("WARN", foreground="#ffd166")
        self.log_tree.tag_configure("WARNING", foreground="#ffd166")
        self.log_tree.tag_configure("ERROR", foreground="#ff8f8f")
        self.log_tree.tag_configure("SUCCESS", foreground="#6ce5b1")
        self._register_scroll_target(self.log_tree, self.log_tree)

        node_panel_wrap = ttk.Frame(parent, style="SoftPanel.TFrame", padding=16)
        node_panel_wrap.grid(row=0, column=1, sticky="nsew")
        node_panel_wrap.columnconfigure(0, weight=1)
        node_panel_wrap.rowconfigure(0, weight=1)
        self.node_logs_container = node_panel_wrap
        self.node_log_canvas = tk.Canvas(node_panel_wrap, bg="#182330", highlightthickness=0)
        self.node_log_canvas.grid(row=0, column=0, sticky="nsew")
        node_scroll = ttk.Scrollbar(node_panel_wrap, orient="vertical", command=self.node_log_canvas.yview)
        node_scroll.grid(row=0, column=1, sticky="ns")
        self.node_log_canvas.configure(yscrollcommand=node_scroll.set)
        self.node_log_panel = ttk.Frame(self.node_log_canvas, style="SoftPanel.TFrame")
        self.node_log_window = self.node_log_canvas.create_window((0, 0), window=self.node_log_panel, anchor="nw")
        self.node_log_panel.columnconfigure(0, weight=1)
        self.node_log_panel.bind("<Configure>", lambda _e: self.node_log_canvas.configure(scrollregion=self.node_log_canvas.bbox("all")) if self.node_log_canvas is not None else None)
        self.node_log_canvas.bind("<Configure>", self._on_node_log_canvas_configure)
        self.node_logs_title = ttk.Label(self.node_log_panel, text="监控状态", style="PanelTitle.TLabel")
        self.node_logs_title.grid(row=0, column=0, sticky="w")
        self.node_log_empty_label = ttk.Label(self.node_log_panel, text="等待节点连接或节点状态更新。", style="Foot.TLabel")
        self.node_log_empty_label.grid(row=1, column=0, sticky="w", pady=(8, 0))

    def _build_embedded_knowledge_panel(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)
        header = ttk.Frame(parent, style="Panel.TFrame", padding=16)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="知识中心", style="Header.TLabel").grid(row=0, column=0, sticky="w")

        control = ttk.Frame(parent, style="Panel.TFrame", padding=16)
        control.grid(row=1, column=0, sticky="nsew", pady=(14, 0))
        control.columnconfigure(0, weight=3)
        control.columnconfigure(1, weight=2)
        control.rowconfigure(1, weight=1)

        topbar = ttk.Frame(control, style="SoftPanel.TFrame", padding=12)
        topbar.grid(row=0, column=0, columnspan=2, sticky="ew")
        topbar.columnconfigure(1, weight=1)
        topbar.columnconfigure(2, weight=1)
        ttk.Label(topbar, text="导入目标", style="Body.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 8))
        self.kb_scope_combo = ttk.Combobox(topbar, state="readonly")
        self.kb_scope_combo.grid(row=0, column=1, columnspan=2, sticky="ew", padx=(10, 0), pady=(0, 8))
        options_bar = ttk.Frame(topbar, style="SoftPanel.TFrame")
        options_bar.grid(row=1, column=0, columnspan=3, sticky="ew")
        options_bar.columnconfigure(0, weight=1)
        options_bar.columnconfigure(1, weight=1)
        ttk.Checkbutton(options_bar, text="导入前重建当前作用域索引", variable=self.kb_reset_var).grid(row=0, column=0, sticky="w", padx=(0, 12))
        ttk.Checkbutton(options_bar, text="同步写入结构化知识库", variable=self.kb_structured_var).grid(row=0, column=1, sticky="w")
        action_bar = ttk.Frame(topbar, style="SoftPanel.TFrame")
        action_bar.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(10, 0))
        self._grid_action_bar(
            action_bar,
            [
                ttk.Button(action_bar, text="导入文本 / 表格", command=self._import_knowledge_files),
                ttk.Button(action_bar, text="导入语音 / 视频 / 图片", command=self._import_knowledge_media_files),
                ttk.Button(action_bar, text="导入整个文件夹", command=self._import_knowledge_folder),
                ttk.Button(action_bar, text="导入公共背景库", command=lambda: self._import_knowledge_files("common")),
                ttk.Button(action_bar, text="刷新知识库", command=self._refresh_knowledge_bases),
            ],
            columns=5,
        )

        table_wrap = ttk.Frame(control, style="SoftPanel.TFrame", padding=12)
        table_wrap.grid(row=1, column=0, sticky="nsew", pady=(14, 0), padx=(0, 10))
        table_wrap.columnconfigure(0, weight=1)
        table_wrap.rowconfigure(0, weight=1)
        self.kb_tree = ttk.Treeview(table_wrap, columns=("scope", "title", "docs", "vector", "structured"), show="headings")
        self.kb_tree.heading("scope", text="作用域")
        self.kb_tree.heading("title", text="名称")
        self.kb_tree.heading("docs", text="文件数")
        self.kb_tree.heading("vector", text="索引状态")
        self.kb_tree.heading("structured", text="结构化库")
        self.kb_tree.column("scope", width=220, anchor="w")
        self.kb_tree.column("title", width=240, anchor="w")
        self.kb_tree.column("docs", width=80, anchor="center")
        self.kb_tree.column("vector", width=110, anchor="center")
        self.kb_tree.column("structured", width=110, anchor="center")
        self.kb_tree.grid(row=0, column=0, sticky="nsew")
        self.kb_tree.bind("<<TreeviewSelect>>", self._on_kb_tree_select)
        table_scroll = ttk.Scrollbar(table_wrap, orient="vertical", command=self.kb_tree.yview)
        table_scroll.grid(row=0, column=1, sticky="ns")
        self.kb_tree.configure(yscrollcommand=table_scroll.set)

        detail_wrap = ttk.Frame(control, style="SoftPanel.TFrame", padding=12)
        detail_wrap.grid(row=1, column=1, sticky="nsew", pady=(14, 0))
        detail_wrap.columnconfigure(0, weight=1)
        detail_wrap.rowconfigure(1, weight=1)
        ttk.Label(detail_wrap, text="作用域详情", style="PanelTitle.TLabel").grid(row=0, column=0, sticky="w")
        self.kb_detail_text = tk.Text(detail_wrap, bg="#0f1720", fg="#dbe6f2", insertbackground="#dbe6f2", relief="flat", font=("Microsoft YaHei UI", 10), wrap="word")
        self.kb_detail_text.grid(row=1, column=0, sticky="nsew", pady=(12, 0))
        self.kb_detail_text.configure(state="disabled")

        footer = ttk.Frame(parent, style="Panel.TFrame", padding=(10, 12))
        footer.grid(row=2, column=0, sticky="ew", pady=(16, 0))
        footer.columnconfigure(0, weight=1)
        kb_status_label = ttk.Label(footer, textvariable=self.kb_status_var, style="Foot.TLabel", justify="left")
        kb_status_label.grid(row=0, column=0, sticky="ew")
        self._register_adaptive_wrap_label(kb_status_label, footer, padding=24, min_width=320, max_width=1280)

    def _build_embedded_expert_panel(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)
        header = ttk.Frame(parent, style="Panel.TFrame", padding=16)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="专家中心", style="Header.TLabel").grid(row=0, column=0, sticky="w")

        body = ttk.Frame(parent, style="Panel.TFrame", padding=16)
        body.grid(row=1, column=0, sticky="nsew", pady=(14, 0))
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(1, weight=1)
        topbar = ttk.Frame(body, style="SoftPanel.TFrame", padding=12)
        topbar.grid(row=0, column=0, columnspan=2, sticky="ew")
        self._grid_action_bar(
            topbar,
            [
                ttk.Button(topbar, text="导入模型文件", command=lambda: self._import_selected_expert_assets(False)),
                ttk.Button(topbar, text="导入模型", command=lambda: self._import_selected_expert_assets(True)),
                ttk.Button(topbar, text="导入该专家知识文本", command=self._import_selected_expert_knowledge_text),
                ttk.Button(topbar, text="导入该专家媒体知识", command=self._import_selected_expert_knowledge_media),
                ttk.Button(topbar, text="刷新专家", command=self._refresh_expert_catalog),
            ],
            columns=5,
        )
        table_wrap = ttk.Frame(body, style="SoftPanel.TFrame", padding=12)
        table_wrap.grid(row=1, column=0, sticky="nsew", pady=(14, 0), padx=(0, 10))
        table_wrap.columnconfigure(0, weight=1)
        table_wrap.rowconfigure(0, weight=1)
        self.expert_tree = ttk.Treeview(table_wrap, columns=("name", "category", "asset", "kb"), show="headings")
        self.expert_tree.heading("name", text="专家名称")
        self.expert_tree.heading("category", text="类别")
        self.expert_tree.heading("asset", text="模型状态")
        self.expert_tree.heading("kb", text="知识库状态")
        self.expert_tree.column("name", width=240, anchor="w")
        self.expert_tree.column("category", width=120, anchor="center")
        self.expert_tree.column("asset", width=100, anchor="center")
        self.expert_tree.column("kb", width=110, anchor="center")
        self.expert_tree.grid(row=0, column=0, sticky="nsew")
        self.expert_tree.bind("<<TreeviewSelect>>", self._on_expert_tree_select)
        expert_scroll = ttk.Scrollbar(table_wrap, orient="vertical", command=self.expert_tree.yview)
        expert_scroll.grid(row=0, column=1, sticky="ns")
        self.expert_tree.configure(yscrollcommand=expert_scroll.set)

        detail_wrap = ttk.Frame(body, style="SoftPanel.TFrame", padding=12)
        detail_wrap.grid(row=1, column=1, sticky="nsew", pady=(14, 0))
        detail_wrap.columnconfigure(0, weight=1)
        detail_wrap.rowconfigure(1, weight=1)
        ttk.Label(detail_wrap, text="专家详情", style="PanelTitle.TLabel").grid(row=0, column=0, sticky="w")
        self.expert_detail_text = tk.Text(detail_wrap, bg="#0f1720", fg="#dbe6f2", insertbackground="#dbe6f2", relief="flat", font=("Microsoft YaHei UI", 10), wrap="word")
        self.expert_detail_text.grid(row=1, column=0, sticky="nsew", pady=(12, 0))
        self.expert_detail_text.configure(state="disabled")

        footer = ttk.Frame(parent, style="Panel.TFrame", padding=(10, 12))
        footer.grid(row=2, column=0, sticky="ew", pady=(16, 0))
        footer.columnconfigure(0, weight=1)
        expert_status_label = ttk.Label(footer, textvariable=self.expert_status_var, style="Foot.TLabel", justify="left")
        expert_status_label.grid(row=0, column=0, sticky="ew")
        self._register_adaptive_wrap_label(expert_status_label, footer, padding=24, min_width=320, max_width=1280)

    def _build_embedded_cloud_panel(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)
        header = ttk.Frame(parent, style="Panel.TFrame", padding=16)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="模型配置", style="Header.TLabel").grid(row=0, column=0, sticky="w")

        body = ttk.Frame(parent, style="Panel.TFrame", padding=16)
        body.grid(row=1, column=0, sticky="nsew", pady=(14, 0))
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(0, weight=1)

        session_panel = ttk.Frame(body, style="SoftPanel.TFrame", padding=16)
        session_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        session_panel.columnconfigure(0, weight=1)
        ttk.Label(session_panel, text="运行会话", style="PanelTitle.TLabel").grid(row=0, column=0, sticky="w")

        self.form = ttk.Frame(session_panel, style="SoftPanel.TFrame")
        self.form.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        self.form.columnconfigure(0, weight=1)
        self.backend_combo = self._add_labeled_combo(self.form, 0, "AI模型")
        model_wrapper = ttk.Frame(self.form, style="SoftPanel.TFrame")
        model_wrapper.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        model_wrapper.columnconfigure(0, weight=1)
        ttk.Label(model_wrapper, text="模型选择", style="Body.TLabel").grid(row=0, column=0, columnspan=2, sticky="w")
        self.model_combo = ttk.Combobox(model_wrapper, state="readonly")
        self.model_combo.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        self.model_delete_button = ttk.Button(model_wrapper, text="删除", width=6, command=self._delete_selected_model)
        self.model_delete_button.grid(row=1, column=1, sticky="e", padx=(8, 0), pady=(6, 0))
        self.custom_entry = self._add_labeled_entry(self.form, 2, "自定义 / 导入模型")
        self.custom_entry.master.grid_remove()
        self.mode_combo = self._add_labeled_combo(self.form, 3, "运行模式")
        self.expected_entry = self._add_labeled_entry(self.form, 4, "预期节点数")
        session_actions = ttk.Frame(session_panel, style="SoftPanel.TFrame")
        session_actions.grid(row=2, column=0, sticky="ew", pady=(14, 0))
        self._grid_action_bar(
            session_actions,
            [
                ttk.Button(session_actions, text="刷新模型", command=self._refresh_models),
            ],
            columns=1,
        )

        cloud_panel = ttk.Frame(body, style="SoftPanel.TFrame", padding=16)
        cloud_panel.grid(row=0, column=1, sticky="nsew")
        cloud_panel.columnconfigure(0, weight=1)
        ttk.Label(cloud_panel, text="服务接入", style="PanelTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(cloud_panel, text="当前AI模型", style="Body.TLabel").grid(row=1, column=0, sticky="w", pady=(12, 0))
        self.cloud_provider_combo = ttk.Combobox(cloud_panel, state="readonly")
        self.cloud_provider_combo.grid(row=2, column=0, sticky="ew", pady=(6, 10))
        self.cloud_provider_combo.bind("<<ComboboxSelected>>", lambda _event: self._load_selected_cloud_backend_into_form())
        self.cloud_api_key_entry = self._add_labeled_entry(cloud_panel, 3, "API Key")
        self.cloud_base_url_entry = self._add_labeled_entry(cloud_panel, 4, "Base URL")
        self.cloud_model_entry = self._add_labeled_entry(cloud_panel, 5, "默认模型")
        self.cloud_model_alias_entry = self._add_labeled_entry(cloud_panel, 6, "模型命名")
        actions = ttk.Frame(cloud_panel, style="SoftPanel.TFrame")
        actions.grid(row=7, column=0, sticky="ew", pady=(8, 0))
        self._grid_action_bar(
            actions,
            [
                ttk.Button(actions, text="添加配置", command=self._save_cloud_backend_from_form),
                ttk.Button(actions, text="刷新列表", command=self._refresh_cloud_backend_catalog),
            ],
            columns=2,
        )
        footer = ttk.Frame(parent, style="Panel.TFrame", padding=(10, 12))
        footer.grid(row=2, column=0, sticky="ew", pady=(16, 0))
        footer.columnconfigure(0, weight=1)
        cloud_status_label = ttk.Label(footer, textvariable=self.cloud_status_var, style="Foot.TLabel", justify="left")
        cloud_status_label.grid(row=0, column=0, sticky="ew")
        self._register_adaptive_wrap_label(cloud_status_label, footer, padding=24, min_width=320, max_width=1280)

    def _build_embedded_training_panel(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)
        header = ttk.Frame(parent, style="Panel.TFrame", padding=16)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="训练中心", style="Header.TLabel").grid(row=0, column=0, sticky="w")
        body = ttk.Frame(parent, style="Panel.TFrame", padding=16)
        body.grid(row=1, column=0, sticky="nsew", pady=(14, 0))
        body.columnconfigure(0, weight=1)
        body.rowconfigure(3, weight=1)

        form = ttk.Frame(body, style="SoftPanel.TFrame", padding=12)
        form.grid(row=0, column=0, sticky="ew")
        form.columnconfigure(1, weight=1)
        ttk.Label(form, text="工作区名称", style="Body.TLabel").grid(row=0, column=0, sticky="w")
        self.training_workspace_entry = ttk.Entry(form)
        self.training_workspace_entry.grid(row=0, column=1, sticky="ew", padx=(10, 0))
        self.training_workspace_entry.insert(0, str(get_config("training.workspace_name", "neurolab_hub_training")))

        common_actions = ttk.Frame(body, style="SoftPanel.TFrame", padding=12)
        common_actions.grid(row=1, column=0, sticky="ew", pady=(14, 0))
        self._grid_action_bar(
            common_actions,
            [
                ttk.Button(common_actions, text="构建工作区", command=self._build_training_workspace_from_form),
                ttk.Button(common_actions, text="一键全流程", command=self._start_full_training_from_form),
                ttk.Button(common_actions, text="刷新概览", command=self._refresh_training_overview),
            ],
            columns=3,
        )

        self.training_notebook = ttk.Notebook(body)
        self.training_notebook.grid(row=2, column=0, sticky="nsew", pady=(14, 0))

        llm_tab = ttk.Frame(self.training_notebook, style="Panel.TFrame", padding=14)
        llm_tab.columnconfigure(0, weight=1)
        ttk.Label(llm_tab, text="LLM 训练工作台", style="PanelTitle.TLabel").grid(row=0, column=0, sticky="w")
        llm_form = ttk.Frame(llm_tab, style="SoftPanel.TFrame", padding=12)
        llm_form.grid(row=1, column=0, sticky="ew", pady=(14, 0))
        llm_form.columnconfigure(1, weight=1)
        ttk.Label(llm_form, text="LLM 基础模型", style="Body.TLabel").grid(row=0, column=0, sticky="w")
        self.training_base_model_entry = ttk.Entry(llm_form)
        self.training_base_model_entry.grid(row=0, column=1, sticky="ew", padx=(10, 0))
        self.training_base_model_entry.insert(0, str(get_config("training.llm_base_model", "")))
        llm_actions = ttk.Frame(llm_tab, style="SoftPanel.TFrame", padding=12)
        llm_actions.grid(row=2, column=0, sticky="ew", pady=(14, 0))
        self._grid_action_bar(
            llm_actions,
            [
                ttk.Button(llm_actions, text="导入 LLM 数据", command=self._import_llm_dataset_from_dialog),
                ttk.Button(llm_actions, text="启动 LLM 训练", command=self._start_llm_training_from_form),
            ],
            columns=2,
        )

        vision_tab = ttk.Frame(self.training_notebook, style="Panel.TFrame", padding=14)
        vision_tab.columnconfigure(0, weight=1)
        vision_tab.rowconfigure(4, weight=1)
        ttk.Label(vision_tab, text="YOLO 训练工作台", style="PanelTitle.TLabel").grid(row=0, column=0, sticky="w")
        vision_form = ttk.Frame(vision_tab, style="SoftPanel.TFrame", padding=12)
        vision_form.grid(row=1, column=0, sticky="ew", pady=(14, 0))
        vision_form.columnconfigure(1, weight=1)
        ttk.Label(vision_form, text="YOLO 基础权重", style="Body.TLabel").grid(row=0, column=0, sticky="w")
        self.training_pi_weights_entry = ttk.Entry(vision_form)
        self.training_pi_weights_entry.grid(row=0, column=1, sticky="ew", padx=(10, 0))
        self.training_pi_weights_entry.insert(0, str(get_config("training.pi_base_weights", "yolov8n.pt")))
        vision_actions = ttk.Frame(vision_tab, style="SoftPanel.TFrame", padding=12)
        vision_actions.grid(row=2, column=0, sticky="ew", pady=(14, 0))
        self._grid_action_bar(
            vision_actions,
            [
                ttk.Button(vision_actions, text="导入 YOLO 数据", command=self._import_pi_dataset_from_dialog),
                ttk.Button(vision_actions, text="启动 YOLO 训练", command=self._start_pi_training_from_form),
            ],
            columns=2,
        )
        annotation_actions = ttk.Frame(vision_tab, style="SoftPanel.TFrame", padding=12)
        annotation_actions.grid(row=3, column=0, sticky="ew", pady=(14, 0))
        self._grid_action_bar(
            annotation_actions,
            [
                ttk.Button(annotation_actions, text="导入待标注图片", command=self._import_training_annotation_images),
                ttk.Button(annotation_actions, text="生成测试图片", command=self._generate_training_annotation_samples),
                ttk.Button(annotation_actions, text="刷新标注面板", command=self._refresh_training_annotation_panel),
            ],
            columns=3,
        )

        annotation_panel = ttk.Frame(vision_tab, style="SoftPanel.TFrame", padding=12)
        annotation_panel.grid(row=4, column=0, sticky="nsew", pady=(14, 0))
        annotation_panel.columnconfigure(0, weight=2)
        annotation_panel.columnconfigure(1, weight=5)
        annotation_panel.columnconfigure(2, weight=3)
        annotation_panel.rowconfigure(0, weight=1)

        image_list_wrap = ttk.Frame(annotation_panel, style="Panel.TFrame", padding=10)
        image_list_wrap.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        image_list_wrap.columnconfigure(0, weight=1)
        image_list_wrap.rowconfigure(1, weight=1)
        ttk.Label(image_list_wrap, text="待标注图片", style="PanelTitle.TLabel").grid(row=0, column=0, sticky="w")
        self.training_annotation_tree = ttk.Treeview(image_list_wrap, columns=("image", "boxes"), show="headings", height=12)
        self.training_annotation_tree.heading("image", text="图片")
        self.training_annotation_tree.heading("boxes", text="框数")
        self.training_annotation_tree.column("image", width=180, anchor="w")
        self.training_annotation_tree.column("boxes", width=56, anchor="center")
        self.training_annotation_tree.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
        tree_scroll = ttk.Scrollbar(image_list_wrap, orient="vertical", command=self.training_annotation_tree.yview)
        tree_scroll.grid(row=1, column=1, sticky="ns", pady=(10, 0))
        self.training_annotation_tree.configure(yscrollcommand=tree_scroll.set)
        self.training_annotation_tree.bind("<<TreeviewSelect>>", self._on_training_annotation_select)

        canvas_wrap = ttk.Frame(annotation_panel, style="Panel.TFrame", padding=10)
        canvas_wrap.grid(row=0, column=1, sticky="nsew", padx=(0, 10))
        canvas_wrap.columnconfigure(0, weight=1)
        canvas_wrap.rowconfigure(1, weight=1)
        ttk.Label(canvas_wrap, text="标注画布（拖拽鼠标创建框）", style="PanelTitle.TLabel").grid(row=0, column=0, sticky="w")
        self.training_annotation_canvas = tk.Canvas(canvas_wrap, bg="#081018", highlightthickness=0)
        self.training_annotation_canvas.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
        self.training_annotation_canvas.bind("<Configure>", lambda _event: self._render_training_annotation_image())
        self.training_annotation_canvas.bind("<ButtonPress-1>", self._on_training_annotation_press)
        self.training_annotation_canvas.bind("<B1-Motion>", self._on_training_annotation_drag)
        self.training_annotation_canvas.bind("<ButtonRelease-1>", self._on_training_annotation_release)

        tool_wrap = ttk.Frame(annotation_panel, style="Panel.TFrame", padding=10)
        tool_wrap.grid(row=0, column=2, sticky="nsew")
        tool_wrap.columnconfigure(0, weight=1)
        tool_wrap.rowconfigure(3, weight=1)
        ttk.Label(tool_wrap, text="当前类别", style="PanelTitle.TLabel").grid(row=0, column=0, sticky="w")
        self.training_annotation_class_entry = ttk.Entry(tool_wrap)
        self.training_annotation_class_entry.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        self.training_annotation_class_entry.insert(0, "observation")
        ttk.Label(tool_wrap, text="当前图片标注框", style="PanelTitle.TLabel").grid(row=2, column=0, sticky="w", pady=(14, 0))
        box_wrap = ttk.Frame(tool_wrap, style="Panel.TFrame")
        box_wrap.grid(row=3, column=0, sticky="nsew", pady=(10, 0))
        box_wrap.columnconfigure(0, weight=1)
        box_wrap.rowconfigure(0, weight=1)
        self.training_annotation_box_tree = ttk.Treeview(box_wrap, columns=("id", "class", "w", "h"), show="headings", height=10)
        self.training_annotation_box_tree.heading("id", text="#")
        self.training_annotation_box_tree.heading("class", text="类别")
        self.training_annotation_box_tree.heading("w", text="宽")
        self.training_annotation_box_tree.heading("h", text="高")
        self.training_annotation_box_tree.column("id", width=36, anchor="center")
        self.training_annotation_box_tree.column("class", width=100, anchor="w")
        self.training_annotation_box_tree.column("w", width=50, anchor="center")
        self.training_annotation_box_tree.column("h", width=50, anchor="center")
        self.training_annotation_box_tree.grid(row=0, column=0, sticky="nsew")
        box_scroll = ttk.Scrollbar(box_wrap, orient="vertical", command=self.training_annotation_box_tree.yview)
        box_scroll.grid(row=0, column=1, sticky="ns")
        self.training_annotation_box_tree.configure(yscrollcommand=box_scroll.set)
        box_actions = ttk.Frame(tool_wrap, style="Panel.TFrame")
        box_actions.grid(row=4, column=0, sticky="ew", pady=(12, 0))
        box_actions.columnconfigure(0, weight=1)
        box_actions.columnconfigure(1, weight=1)
        box_actions.columnconfigure(2, weight=1)
        ttk.Button(box_actions, text="保存标注", command=self._save_training_annotations).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ttk.Button(box_actions, text="删除选中框", command=self._delete_selected_training_box).grid(row=0, column=1, sticky="ew", padx=4)
        ttk.Button(box_actions, text="清空当前框", command=self._clear_training_annotation_boxes).grid(row=0, column=2, sticky="ew", padx=(4, 0))
        training_annotation_status_label = ttk.Label(tool_wrap, textvariable=self.training_annotation_status_var, style="Body.TLabel", justify="left")
        training_annotation_status_label.grid(row=5, column=0, sticky="ew", pady=(12, 0))
        self._register_adaptive_wrap_label(training_annotation_status_label, tool_wrap, padding=24, min_width=240, max_width=420)

        self.training_notebook.add(llm_tab, text="LLM 工作台")
        self.training_notebook.add(vision_tab, text="YOLO 工作台")

        detail_wrap = ttk.Frame(body, style="SoftPanel.TFrame", padding=12)
        detail_wrap.grid(row=3, column=0, sticky="nsew", pady=(14, 0))
        detail_wrap.columnconfigure(0, weight=1)
        detail_wrap.rowconfigure(1, weight=1)
        ttk.Label(detail_wrap, text="训练状态", style="PanelTitle.TLabel").grid(row=0, column=0, sticky="w")
        self.training_detail_text = tk.Text(
            detail_wrap,
            bg="#0f1720",
            fg="#dbe6f2",
            insertbackground="#dbe6f2",
            relief="flat",
            font=("Microsoft YaHei UI", 10),
            wrap="word",
        )
        self.training_detail_text.grid(row=1, column=0, sticky="nsew", pady=(12, 0))
        self.training_detail_text.configure(state="disabled")

        footer = ttk.Frame(parent, style="Panel.TFrame", padding=(10, 12))
        footer.grid(row=2, column=0, sticky="ew", pady=(16, 0))
        footer.columnconfigure(0, weight=1)
        training_status_label = ttk.Label(footer, textvariable=self.training_status_var, style="Foot.TLabel", justify="left")
        training_status_label.grid(row=0, column=0, sticky="ew")
        self._register_adaptive_wrap_label(training_status_label, footer, padding=24, min_width=320, max_width=1280)
        self._refresh_training_overview()
        self._refresh_training_annotation_panel()

    def _build_embedded_archive_panel(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)
        header = ttk.Frame(parent, style="Panel.TFrame", padding=16)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="档案中心", style="Header.TLabel").grid(row=0, column=0, sticky="w")

        body = ttk.Frame(parent, style="Panel.TFrame", padding=16)
        body.grid(row=1, column=0, sticky="nsew", pady=(14, 0))
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(0, weight=1)

        table_wrap = ttk.Frame(body, style="SoftPanel.TFrame", padding=12)
        table_wrap.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        table_wrap.columnconfigure(0, weight=1)
        table_wrap.rowconfigure(0, weight=1)
        self.archive_tree = ttk.Treeview(table_wrap, columns=("id", "project", "experiment", "operator", "events", "opened"), show="headings")
        for key, label, width in [("id", "记录", 180), ("project", "项目", 180), ("experiment", "实验", 180), ("operator", "人员", 100), ("events", "事件数", 70), ("opened", "开始时间", 150)]:
            self.archive_tree.heading(key, text=label)
            self.archive_tree.column(key, width=width, anchor="w" if key not in {"events"} else "center")
        self.archive_tree.grid(row=0, column=0, sticky="nsew")
        self.archive_tree.bind("<<TreeviewSelect>>", self._on_archive_tree_select)
        tree_scroll = ttk.Scrollbar(table_wrap, orient="vertical", command=self.archive_tree.yview)
        tree_scroll.grid(row=0, column=1, sticky="ns")
        self.archive_tree.configure(yscrollcommand=tree_scroll.set)

        detail_wrap = ttk.Frame(body, style="SoftPanel.TFrame", padding=12)
        detail_wrap.grid(row=0, column=1, sticky="nsew")
        detail_wrap.columnconfigure(0, weight=1)
        detail_wrap.rowconfigure(1, weight=1)
        ttk.Label(detail_wrap, text="档案详情", style="PanelTitle.TLabel").grid(row=0, column=0, sticky="w")
        self.archive_detail_text = tk.Text(detail_wrap, bg="#0f1720", fg="#dbe6f2", insertbackground="#dbe6f2", relief="flat", font=("Microsoft YaHei UI", 10), wrap="word")
        self.archive_detail_text.grid(row=1, column=0, sticky="nsew", pady=(12, 0))
        self.archive_detail_text.configure(state="disabled")

        footer = ttk.Frame(parent, style="Panel.TFrame", padding=(10, 12))
        footer.grid(row=2, column=0, sticky="ew", pady=(16, 0))
        footer.columnconfigure(0, weight=1)
        archive_status_label = ttk.Label(footer, textvariable=self.archive_status_var, style="Foot.TLabel", justify="left")
        archive_status_label.grid(row=0, column=0, sticky="ew")
        self._register_adaptive_wrap_label(archive_status_label, footer, padding=24, min_width=320, max_width=1280)
        ttk.Button(footer, text="刷新档案", command=self._refresh_archive_catalog).grid(row=0, column=1, sticky="e")

    def _show_startup_splash(self) -> None:
        splash = tk.Toplevel(self.root)
        splash.configure(bg="#071018")
        splash.attributes("-topmost", True)
        splash.title(f"{APP_DISPLAY_NAME} 正在启动")
        splash.resizable(False, False)
        self.splash = splash
        splash.protocol("WM_DELETE_WINDOW", self._on_close)

        width = self._scaled(700)
        height = self._scaled(250)
        screen_w = splash.winfo_screenwidth()
        screen_h = splash.winfo_screenheight()
        offset_x = int((screen_w - width) / 2)
        offset_y = int((screen_h - height) / 2)
        splash.geometry(f"{width}x{height}+{offset_x}+{offset_y}")

        panel = ttk.Frame(splash, style="Panel.TFrame", padding=(self._scaled(16), self._scaled(14)))
        panel.pack(fill="both", expand=True)
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(0, weight=1)

        content = ttk.Frame(panel, style="Panel.TFrame")
        content.grid(row=0, column=0, sticky="nw")
        content.columnconfigure(0, weight=0)
        content.columnconfigure(1, weight=1)

        logo_holder = ttk.Frame(content, style="Panel.TFrame")
        logo_holder.grid(row=0, column=0, sticky="nw", padx=(0, self._scaled(16)), pady=(self._scaled(2), 0))
        self.splash_logo_image = self._load_logo_image((64, 64))
        if self.splash_logo_image is not None:
            tk.Label(logo_holder, image=self.splash_logo_image, bg="#182330").pack(anchor="center", pady=(self._scaled(6), 0))
        else:
            tk.Label(
                logo_holder,
                text="LD",
                bg="#0b1e2d",
                fg="#78e6ff",
                font=("Bahnschrift", 22, "bold"),
                padx=self._scaled(16),
                pady=self._scaled(16),
            ).pack(anchor="center", pady=(self._scaled(6), 0))

        text_holder = ttk.Frame(content, style="Panel.TFrame")
        text_holder.grid(row=0, column=1, sticky="nsew")
        text_holder.columnconfigure(0, weight=1)
        wraplength = self._scaled(460)
        row = 0
        title_label = ttk.Label(text_holder, text=APP_DISPLAY_NAME, style="SplashTitle.TLabel")
        title_label.grid(row=row, column=0, sticky="ew", pady=(self._scaled(2), 0))
        row += 1
        tagline_label = ttk.Label(text_holder, text=APP_SHORT_TAGLINE, style="Brand.TLabel")
        tagline_label.grid(row=row, column=0, sticky="w", pady=(self._scaled(6), 0))
        row += 1
        meta_label = ttk.Label(
            text_holder,
            text=f"桌面版 v{self.app_version} | {COMPANY_NAME}",
            style="SplashMeta.TLabel",
        )
        meta_label.grid(row=row, column=0, sticky="w", pady=(self._scaled(4), 0))
        row += 1
        status_row = ttk.Frame(text_holder, style="Panel.TFrame")
        status_row.grid(row=row, column=0, sticky="ew", pady=(self._scaled(10), 0))
        status_row.columnconfigure(1, weight=1)
        tk.Label(
            status_row,
            text="启动中",
            bg="#1fb68d",
            fg="#0f1720",
            font=("Microsoft YaHei UI", 9, "bold"),
            padx=self._scaled(10),
            pady=self._scaled(4),
        ).grid(row=0, column=0, sticky="w")
        status_label = ttk.Label(
            status_row,
            textvariable=self.splash_message_var,
            style="SplashStatus.TLabel",
            wraplength=wraplength - self._scaled(90),
        )
        status_label.grid(row=0, column=1, sticky="w", padx=(self._scaled(10), 0))
        row += 1
        detail_label = ttk.Label(
            text_holder,
            textvariable=self.splash_detail_var,
            style="SplashHint.TLabel",
            wraplength=wraplength,
        )
        detail_label.grid(row=row, column=0, sticky="w", pady=(self._scaled(6), 0))
        row += 1
        progress = ttk.Progressbar(
            text_holder,
            mode="determinate",
            variable=self.splash_progress_var,
            maximum=100,
            length=self._scaled(360),
        )
        progress.grid(row=row, column=0, sticky="w", pady=(self._scaled(12), 0))
        splash.update_idletasks()
        text_column_width = max(
            self._scaled(320),
            title_label.winfo_reqwidth(),
            tagline_label.winfo_reqwidth(),
            meta_label.winfo_reqwidth(),
            status_row.winfo_reqwidth(),
            detail_label.winfo_reqwidth(),
        )
        progress.configure(length=text_column_width)
        splash.update_idletasks()
        logo_block_width = max(self._scaled(64), logo_holder.winfo_reqwidth())
        right_margin = max(self._scaled(18), logo_block_width)
        actual_width = logo_block_width + self._scaled(16) + text_column_width + right_margin
        actual_height = max(content.winfo_reqheight() + self._scaled(28), self._scaled(220))
        offset_x = int((screen_w - actual_width) / 2)
        offset_y = int((screen_h - actual_height) / 2)
        splash.geometry(f"{actual_width}x{actual_height}+{offset_x}+{offset_y}")
        splash.update_idletasks()
        self._apply_close_only_window_style(splash)

    def _load_logo_image(self, size: tuple[int, int]) -> ImageTk.PhotoImage | None:
        try:
            logo_file = logo_path()
            if not logo_file.exists():
                return None
            return ImageTk.PhotoImage(Image.open(logo_file).resize(size, Image.Resampling.LANCZOS))
        except Exception:
            return None

    def _set_startup_progress(
        self,
        value: float,
        message: str | None = None,
        step: str | None = None,
        detail: str | None = None,
    ) -> None:
        self.splash_progress_var.set(max(0.0, min(100.0, float(value))))
        if message is not None:
            self.splash_message_var.set(message)
        if step is not None:
            self.splash_step_var.set(f"当前步骤：{step}")
        if detail is not None:
            self.splash_detail_var.set(detail)
        if self.splash is not None:
            try:
                self.splash.update_idletasks()
            except Exception:
                pass

    def _grid_action_bar(self, parent: ttk.Frame, widgets: List[tk.Widget], *, columns: int = 4) -> None:
        """把顶部操作栏按可拉伸网格排布，避免低分辨率下单行挤压。"""
        total_columns = max(1, int(columns))
        for column in range(total_columns):
            parent.columnconfigure(column, weight=1, uniform="action-bar")
        for index, widget in enumerate(widgets):
            row = index // total_columns
            column = index % total_columns
            padx = (0, 8) if column < total_columns - 1 else (0, 0)
            pady = (0, 8) if row == 0 else (0, 0)
            widget.grid(row=row, column=column, sticky="ew", padx=padx, pady=pady)

    def _normalize_startup_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        value = float(payload.get("value", self.splash_progress_var.get()))
        message = str(payload.get("message") or self.splash_message_var.get())
        step = str(payload.get("step") or self.splash_step_var.get().replace("当前步骤：", "", 1))
        detail = str(payload.get("detail") or self.splash_detail_var.get())

        if value < 18:
            return {
                "value": max(10.0, value),
                "message": "正在初始化运行环境",
                "step": "环境检查",
                "detail": "正在检查运行环境、基础依赖与本地资源",
            }
        if value < 82:
            return {
                "value": value,
                "message": "正在执行启动自检",
                "step": step,
                "detail": detail,
            }
        if value < 92:
            return {
                "value": 82.0,
                "message": "正在加载配置与模型",
                "step": "配置加载",
                "detail": "正在同步主界面所需的配置、模型与知识资源",
            }
        if value < 99:
            return {
                "value": 92.0,
                "message": "正在完成主界面准备",
                "step": "界面就绪",
                "detail": "正在同步运行状态、监控区域和系统事件",
            }
        if value < 100:
            return {
                "value": 99.0,
                "message": "正在启动工作台界面",
                "step": "界面收尾",
                "detail": "正在挂载主工作台视图并完成启动前的最后准备",
            }
        return {
            "value": 100.0,
            "message": message,
            "step": step,
            "detail": detail,
        }

    def _finish_startup(self) -> None:
        self._set_startup_progress(100, "主界面准备完成", "启动完成", "主界面、基础服务与启动自检均已就绪")
        if self.splash is not None:
            try:
                self.splash.destroy()
            except Exception:
                pass
            self.splash = None
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()
        self._start_background_orchestrator_prepare()
        if self.skip_startup_splash and self.runtime is not None and not getattr(self.runtime, "self_check_has_run", False):
            self._start_background_startup_self_check()
        if bool(get_config("ui.prompt_voice_test_on_startup", False)):
            self.root.after(800, self._offer_voice_test)

    def _log_gui_action(self, action: str, **payload: Any) -> None:
        try:
            stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            text = f"{stamp} | {action}"
            if payload:
                compact = ", ".join(f"{key}={payload[key]!r}" for key in sorted(payload))
                text = f"{text} | {compact}"
            encoding = "utf-8-sig" if not self.gui_log_path.exists() else "utf-8"
            with self.gui_log_path.open("a", encoding=encoding) as fp:
                fp.write(text + "\n")
        except Exception:
            pass

    def _log_autonomy_action(self, action: str, **payload: Any) -> None:
        """把应用内自治动作同时写入 GUI 动作日志和系统事件流。"""
        self._log_gui_action(action, **payload)
        if self.runtime is None:
            return
        try:
            compact = ", ".join(
                f"{key}={payload[key]!r}"
                for key in sorted(payload)
                if key not in {"result", "result_text"}
            ) if payload else ""
            result_text = str(payload.get("result_text") or payload.get("result") or "").strip()
            detail = f"[AUTONOMY] 管家已执行动作: {action}"
            if result_text:
                detail = f"{detail} -> {result_text}"
            if compact:
                detail = f"{detail} | {compact}"
            self.runtime._log_raw_line(detail, level="INFO")
        except Exception:
            pass

    def _add_labeled_combo(self, parent: ttk.Frame, row: int, label: str) -> ttk.Combobox:
        wrapper = ttk.Frame(parent, style="SoftPanel.TFrame")
        wrapper.grid(row=row, column=0, sticky="ew", pady=(0, 10))
        wrapper.columnconfigure(0, weight=1)
        ttk.Label(wrapper, text=label, style="Body.TLabel").grid(row=0, column=0, sticky="w")
        combo = ttk.Combobox(wrapper, state="readonly")
        combo.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        return combo

    def _add_labeled_entry(self, parent: ttk.Frame, row: int, label: str) -> ttk.Entry:
        wrapper = ttk.Frame(parent, style="SoftPanel.TFrame")
        wrapper.grid(row=row, column=0, sticky="ew", pady=(0, 10))
        wrapper.columnconfigure(0, weight=1)
        ttk.Label(wrapper, text=label, style="Body.TLabel").grid(row=0, column=0, sticky="w")
        entry = ttk.Entry(wrapper)
        entry.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        return entry

    def _register_adaptive_wrap_label(
        self,
        label: ttk.Label,
        container: Any | None = None,
        *,
        padding: int = 32,
        min_width: int = 220,
        max_width: int = 960,
    ) -> ttk.Label:
        """让长文本标签跟随容器宽度自动换行，避免窗口初次打开时遮挡错位。"""
        target = container or getattr(label, "master", None) or self.root

        def _apply(_event: Any | None = None) -> None:
            try:
                if not label.winfo_exists() or not target.winfo_exists():
                    return
                width = int(target.winfo_width() or 0)
                if width <= 1:
                    return
                wraplength = max(min_width, min(width - padding, max_width))
                label.configure(wraplength=wraplength)
            except Exception:
                return

        try:
            target.bind("<Configure>", _apply, add="+")
        except Exception:
            pass
        self.root.after_idle(_apply)
        return label

    def _bind_events(self) -> None:
        self.backend_combo.bind("<<ComboboxSelected>>", lambda _event: self._update_model_choices())
        self.model_combo.bind("<<ComboboxSelected>>", lambda _event: self._handle_model_selection())
        self.mode_combo.bind("<<ComboboxSelected>>", lambda _event: self._sync_field_visibility())
        self.root.bind("<Configure>", self._on_root_configure)
        self.root.bind("<F11>", lambda _event: self._toggle_demo_mode())
        self.root.bind("<Escape>", lambda _event: self._handle_escape_key())
        self._bind_global_scroll_support()

    def _visible_backend_rows(self, rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
        by_backend: Dict[str, Dict[str, str]] = {}
        for row in rows:
            backend = str(row.get("value") or row.get("backend") or "")
            if backend not in VISIBLE_BACKENDS:
                continue
            label = BACKEND_LABEL_OVERRIDES.get(backend, str(row.get("label") or backend))
            normalized = dict(row)
            normalized["label"] = label
            by_backend[backend] = normalized
        filtered: List[Dict[str, str]] = []
        for backend in VISIBLE_BACKENDS:
            row = by_backend.get(backend)
            if row is not None:
                filtered.append(row)
        return filtered

    def _configurable_backend_rows(self, rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
        by_backend: Dict[str, Dict[str, str]] = {}
        for row in rows:
            backend = str(row.get("value") or row.get("backend") or "")
            if backend not in CONFIG_BACKENDS:
                continue
            label = BACKEND_LABEL_OVERRIDES.get(backend, str(row.get("label") or backend))
            normalized = dict(row)
            normalized["label"] = label
            by_backend[backend] = normalized
        filtered: List[Dict[str, str]] = []
        for backend in CONFIG_BACKENDS:
            row = by_backend.get(backend)
            if row is not None:
                filtered.append(row)
        return filtered

    def _load_custom_model_registry(self) -> None:
        raw = str(get_config("desktop_ui.custom_models", "{}") or "{}").strip()
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                normalized_registry: Dict[str, List[Dict[str, str]]] = {}
                for key, value in parsed.items():
                    if not isinstance(value, list):
                        continue
                    entries: List[Dict[str, str]] = []
                    for item in value:
                        if isinstance(item, str):
                            model_name = item.strip()
                            if model_name:
                                entries.append({"name": model_name, "model": model_name})
                        elif isinstance(item, dict):
                            name = str(item.get("name") or "").strip()
                            model = str(item.get("model") or name).strip()
                            if name and model:
                                entries.append({"name": name, "model": model})
                    if entries:
                        normalized_registry[str(key)] = entries
                self.custom_model_registry = normalized_registry
                return
        except Exception:
            pass
        self.custom_model_registry = {}

    def _save_custom_model_registry(self) -> None:
        set_config("desktop_ui.custom_models", json.dumps(self.custom_model_registry, ensure_ascii=False))

    def _custom_entries_for_backend(self, backend_value: str) -> List[Dict[str, str]]:
        return list(self.custom_model_registry.get(backend_value, []))

    def _custom_model_names_for_backend(self, backend_value: str) -> List[str]:
        names: List[str] = []
        seen: set[str] = set()
        for item in self._custom_entries_for_backend(backend_value):
            name = str(item.get("name") or "").strip()
            if name and name not in seen:
                names.append(name)
                seen.add(name)
        return names

    def _resolve_selected_model_value(self, backend_value: str, selected_name: str) -> str:
        selected_name = str(selected_name or "").strip()
        if not selected_name or selected_name == CUSTOM_MODEL_OPTION:
            return ""
        for item in self._custom_entries_for_backend(backend_value):
            if str(item.get("name") or "").strip() == selected_name:
                return str(item.get("model") or selected_name).strip()
        return selected_name

    def _render_custom_model_chips(self, backend_value: str) -> None:
        return

    def _delete_custom_model(self, model_name: str) -> None:
        backend_value = self.backend_map.get(self.backend_combo.get(), self.backend_var.get() or "ollama")
        items = [
            item
            for item in self._custom_entries_for_backend(backend_value)
            if str(item.get("name") or "").strip() != model_name
        ]
        self.custom_model_registry[backend_value] = items
        self._save_custom_model_registry()
        if self.model_combo.get() == model_name:
            self.model_combo.set("")
        self._update_model_choices()

    def _delete_selected_model(self) -> None:
        backend_value = self.backend_map.get(self.backend_combo.get(), self.backend_var.get() or "ollama")
        model_name = self.model_combo.get().strip()
        custom_items = self._custom_model_names_for_backend(backend_value)
        if not model_name or model_name == CUSTOM_MODEL_OPTION:
            return
        if model_name not in custom_items:
            self.hero_var.set("当前模型不是自定义项，无需删除")
            return
        self._delete_custom_model(model_name)

    def _prompt_add_custom_model(self) -> None:
        backend_value = self.backend_map.get(self.backend_combo.get(), self.backend_var.get() or "ollama")
        value = simpledialog.askstring(
            APP_DISPLAY_NAME,
            "请输入自定义模型名称或你本地训练后的模型标识：",
            parent=self.root,
        )
        if not value:
            self._update_model_choices()
            return
        model_name = value.strip()
        if not model_name:
            self._update_model_choices()
            return
        items = self._custom_entries_for_backend(backend_value)
        if not any(str(item.get("name") or "").strip() == model_name for item in items):
            items.append({"name": model_name, "model": model_name})
        self.custom_model_registry[backend_value] = items
        self._save_custom_model_registry()
        self._update_model_choices(selected_model=model_name)


    def _update_model_choices(self, selected_model: str | None = None) -> None:
        backend_value = self.backend_map.get(self.backend_combo.get(), self.backend_var.get() or "ollama")
        self.backend_var.set(backend_value)
        catalog_models = list(self.model_catalog.get(backend_value, []))
        models = self._recommended_models_for_backend(backend_value, catalog_models)
        for custom_name in self._custom_model_names_for_backend(backend_value):
            if custom_name not in models:
                models.append(custom_name)
        self.model_combo["values"] = models
        desired = selected_model or (models[0] if models else "")
        if desired not in models:
            fallback = models[0] if models else ""
            self.model_combo.set(fallback)
            self.custom_model_var.set(fallback)
        else:
            self.model_combo.set(desired)
            self.custom_model_var.set(desired)
        self._render_custom_model_chips(backend_value)
        self._sync_field_visibility()

    def _sync_field_visibility(self) -> None:
        is_multi = self.mode_map.get(self.mode_combo.get(), self.mode_var.get()) == "websocket"
        self.custom_entry.master.grid_remove()
        if self.model_delete_button is not None:
            backend_value = self.backend_map.get(self.backend_combo.get(), self.backend_var.get() or "ollama")
            current_model = self.model_combo.get().strip()
            custom_items = set(self._custom_model_names_for_backend(backend_value))
            if current_model and current_model in custom_items:
                self.model_delete_button.state(["!disabled"])
            else:
                self.model_delete_button.state(["disabled"])
        self.expected_entry.master.grid() if is_multi else self.expected_entry.master.grid_remove()

    def _handle_model_selection(self) -> None:
        self.custom_model_var.set(self.model_combo.get())
        self._sync_field_visibility()

    def _recommended_models_for_backend(self, backend_value: str, catalog_models: List[str]) -> List[str]:
        if backend_value != "ollama":
            return []
        preferred = RECOMMENDED_MODEL_NAMES.get(backend_value, [])
        ordered: List[str] = []
        seen: set[str] = set()
        for name in preferred:
            if name and name not in seen:
                ordered.append(name)
                seen.add(name)
        current_default = str(self.current_state.get("session", {}).get("model") or "").strip()
        for extra in catalog_models:
            if extra in seen:
                continue
            if extra == current_default and extra:
                ordered.append(extra)
                seen.add(extra)
        for extra in catalog_models:
            if extra in seen:
                continue
            ordered.append(extra)
            seen.add(extra)
        return ordered

    def _dispatch(self, name: str, fn) -> None:
        def runner() -> None:
            try:
                result = fn()
                self.ui_queue.put(("ok", name, result))
            except Exception as exc:
                self.ui_queue.put(("error", name, str(exc)))

        threading.Thread(target=runner, daemon=True, name=f"UI_{name}").start()



    def _selected_kb_scope(self) -> str:
        if self.kb_scope_combo is None:
            return "common"
        return self.kb_scope_map.get(self.kb_scope_combo.get(), "common")








    def _run_self_check(self) -> None:
        self._log_gui_action("click_self_check")
        self.hero_var.set("后台准备中")
        if self.runtime is not None:
            self.runtime.update_local_task_progress(
                {
                    "task_name": "本机系统自检",
                    "stage": "scan",
                    "title": "正在检查本机环境",
                    "detail": "正在检查依赖、内置组件和核心资源。",
                    "percent": 0,
                    "status": "running",
                    "current": 0,
                    "total": 1,
                }
            )
            self.runtime.request_remote_self_checks()
        self._dispatch(
            "self_check",
            lambda: self.runtime.run_self_check(
                include_microphone=False,
                progress_callback=lambda payload: self.ui_queue.put(("progress", "self_check", payload)),
            ),
        )

    def _start_background_startup_self_check(self) -> None:
        if self.startup_self_check_started or self.runtime is None:
            return
        self.startup_self_check_started = True
        self.hero_var.set("后台准备中")
        self._dispatch(
            "startup_self_check",
            lambda: self.runtime.run_self_check(
                include_microphone=False,
                include_voice_assets=False,
                progress_callback=lambda payload: self.ui_queue.put(("progress", "startup_self_check", payload)),
            ),
        )

    def _start_background_orchestrator_prepare(self) -> None:
        if self.orchestrator_prepare_started or self.runtime is None:
            return
        self.orchestrator_prepare_started = True
        self.hero_var.set("后台准备中")
        self._dispatch("orchestrator_prepare", self.runtime.prepare_orchestrator_assets)

    def _offer_voice_test(self) -> None:
        if self.voice_test_prompted:
            return
        self.voice_test_prompted = True
        self._log_gui_action("confirm_voice_test", choice="skip_popup")
        self.hero_var.set("系统已可用")

    def _start_voice_test_from_ui(self) -> None:
        if self.runtime is None:
            self.hero_var.set("系统尚未完成初始化，请稍后再试")
            return
        self._log_gui_action("manual_voice_test")
        self.hero_var.set("正在准备语音交互测试")
        self._dispatch("voice_test", self.runtime.run_voice_test)

    def _start_session(self) -> None:
        try:
            expected_nodes = int(self.expected_entry.get().strip() or "1")
        except ValueError:
            self.hero_var.set("预期节点数必须为整数")
            return

        backend_value = self.backend_map.get(self.backend_combo.get(), "ollama")
        mode_value = self.mode_map.get(self.mode_combo.get(), "camera")
        selected_model = self.model_combo.get()
        selected_model_value = self._resolve_selected_model_value(backend_value, selected_model)
        if not selected_model_value:
            fallback_models = list(self.model_catalog.get(backend_value, []))
            recommended = self._recommended_models_for_backend(backend_value, fallback_models)
            if recommended:
                selected_model = recommended[0]
                selected_model_value = self._resolve_selected_model_value(backend_value, selected_model)
                self.model_combo.set(selected_model)
                self.custom_model_var.set(selected_model)
            elif self.runtime is not None:
                selected_model_value = str(self.runtime._default_model_for(backend_value) or "").strip()
                if selected_model_value:
                    selected_model = selected_model_value
                    self.model_combo.set(selected_model)
                    self.custom_model_var.set(selected_model)
        custom_model = self.custom_entry.get().strip() if selected_model == CUSTOM_MODEL_OPTION else ""
        payload = {
            "ai_backend": backend_value,
            "selected_model": "" if selected_model == CUSTOM_MODEL_OPTION else selected_model_value,
            "custom_model": custom_model,
            "mode": mode_value,
            "expected_nodes": max(expected_nodes, 1),
        }
        self._log_gui_action(
            "click_start_monitor",
            ai_backend=backend_value,
            selected_model=selected_model,
            selected_model_value=selected_model_value,
            custom_model=custom_model,
            mode=mode_value,
            expected_nodes=max(expected_nodes, 1),
        )
        self.hero_var.set("正在启动 NeuroLab Hub 控制台")
        self._dispatch("start_session", lambda: self.runtime.start_session(payload))

    def _stop_session(self) -> None:
        self._log_gui_action("click_stop_monitor")
        self.hero_var.set("正在启动 NeuroLab Hub 控制台")
        self._dispatch("stop_session", self.runtime.stop_session)


    def _refresh_state_tick(self) -> None:
        try:
            if self.is_closing:
                return
            if self.runtime is None:
                return
            self._render_state(self.runtime.get_state(), include_streams=False)
        except Exception as exc:
            self._log_gui_action("state_refresh_error", error=str(exc))
        finally:
            if not self.is_closing and self.root.winfo_exists():
                self.root.after(1200, self._refresh_state_tick)

    def _refresh_streams_tick(self) -> None:
        try:
            if self.is_closing:
                return
            if self.runtime is None:
                return
            state = self.runtime.get_streams_state()
            session = state.get("session", {})
            orchestrator_state = state.get("orchestrator", {})
            phase = str(session.get("phase") or "idle").lower()
            status_message = str(session.get("status_message") or "").strip()
            if phase == "running":
                badge_text = "运行中"
            elif phase == "starting":
                badge_text = "启动中"
            else:
                badge_text = "待机"
            self.hero_var.set(_present_hero_message(status_message, str(orchestrator_state.get("status") or "")))
            self.session_var.set(badge_text)
            self._update_session_badge()
            self._render_task_progress(state.get("tasks", {}))
            self._render_streams(state.get("streams", []))
        except Exception as exc:
            self._log_gui_action("stream_refresh_error", error=str(exc))
        finally:
            if not self.is_closing and self.root.winfo_exists():
                self.stream_refresh_after_id = self.root.after(80, self._refresh_streams_tick)

    def _render_state(self, state: Dict[str, Any], *, include_streams: bool = True) -> None:
        self.current_state = state
        session = state.get("session", {})
        orchestrator_state = state.get("orchestrator", {})
        phase = str(session.get("phase") or "idle").lower()
        status_message = str(session.get("status_message") or "").strip()
        if phase == "running":
            badge_text = "运行中"
        elif phase == "starting":
            badge_text = "启动中"
        else:
            badge_text = "待机"
        self.hero_var.set(_present_hero_message(status_message, str(orchestrator_state.get("status") or "")))
        self.session_var.set(badge_text)
        self._update_session_badge()
        self._render_summary(state)
        self._render_checks(state.get("self_check", []))
        self._render_task_progress(state.get("tasks", {}))
        self._render_logs(state.get("logs", []))
        if include_streams:
            self._render_streams(state.get("streams", []))

    def _update_session_badge(self) -> None:
        if self.session_badge is None:
            return
        session = self.current_state.get("session", {})
        phase = str(session.get("phase") or "idle").lower()
        if phase == "running":
            self.session_badge.configure(bg="#20c997", fg="#0f1720")
        elif phase == "starting":
            self.session_badge.configure(bg="#6ec1ff", fg="#0f1720")
        else:
            self.session_badge.configure(bg="#f6c344", fg="#0f1720")

    def _render_summary(self, state: Dict[str, Any]) -> None:
        summary = state.get("summary", {})
        session = state.get("session", {})
        orchestrator_state = state.get("orchestrator", {})
        mode_label = {
            "idle": "待机",
            "camera": "单机监控",
            "websocket": "WebSocket 模式",
        }.get(str(session.get("mode") or "").lower(), session.get("mode") or "-")
        self.summary_vars["mode"].set(mode_label)
        self.summary_vars["online"].set(str(summary.get("online_nodes", 0)))
        self.summary_vars["offline"].set(str(summary.get("offline_nodes", 0)))
        self.summary_vars["voice"].set("ON" if summary.get("voice_running") else "OFF")
        self.summary_vars["orchestrator"].set(self._format_orchestrator_status(str(orchestrator_state.get("status") or "")))
        self.summary_vars["planner"].set(self._format_planner_backend(str(orchestrator_state.get("planner_backend") or "")))
        self._render_layer_health(state)
        self._render_layer_issue(state)

    def _render_layer_health(self, state: Dict[str, Any]) -> None:
        pc_rows, pi_rows = self._build_layer_rows(state)
        self._fill_layer_cards(self.pc_layer_cards_frame, pc_rows + pi_rows, columns=3)
        self._fill_layer_cards(self.pi_layer_cards_frame, [], columns=1)

    def _build_layer_issue_payload(self, state: Dict[str, Any]) -> Dict[str, str]:
        tasks = dict(state.get("tasks") or {})
        local_task = dict(tasks.get("local") or {})
        summary = dict(state.get("summary") or {})
        orchestrator_state = dict(state.get("orchestrator") or {})
        orchestrator_status = str(orchestrator_state.get("status") or "").lower()
        online_nodes = int(summary.get("online_nodes", 0) or 0)
        expected_nodes = max(1, int(state.get("session", {}).get("expected_nodes", 1) or 1))

        local_status = str(local_task.get("status") or "").lower()
        if local_status in {"running", "error"}:
            detail = str(local_task.get("detail") or "本机仍在检查或补全运行环境。").strip()
            return {
                "title": "发现本机运行环境问题",
                "detail": detail,
                "action_key": "run_self_check",
                "action_label": "查看并修复",
            }
        if orchestrator_status and orchestrator_status != "ready":
            reason = str(orchestrator_state.get("reason") or "固定管家层尚未完成准备。").strip()
            return {
                "title": "发现管家编排层问题",
                "detail": reason,
                "action_key": "repair_orchestrator",
                "action_label": "查看并修复",
            }
        if not self.knowledge_catalog or not self.expert_catalog:
            return {
                "title": "发现知识或专家目录未就绪",
                "detail": "知识库或专家目录尚未刷新完成，可能影响问答与任务调度。",
                "action_key": "refresh_catalogs",
                "action_label": "查看并修复",
            }
        if online_nodes < expected_nodes:
            return {
                "title": "发现节点链路未完全就绪",
                "detail": f"当前在线节点 {online_nodes} 个，低于预期的 {expected_nodes} 个，可发起节点自检并重新同步状态。",
                "action_key": "request_node_checks",
                "action_label": "查看并修复",
            }
        return {}

    def _render_layer_issue(self, state: Dict[str, Any]) -> None:
        payload = self._build_layer_issue_payload(state)
        self.current_layer_issue = payload
        if self.layer_issue_card is None:
            return
        if not payload:
            self.layer_issue_card.grid_remove()
            return
        self.layer_issue_title_var.set(str(payload.get("title") or "发现需要处理的问题"))
        self.layer_issue_detail_var.set(str(payload.get("detail") or "请查看详情并执行修复。"))
        self.layer_issue_action_var.set(str(payload.get("action_label") or "查看并修复"))
        self.layer_issue_card.grid()

    def _repair_selected_layer_issue(self) -> None:
        action_key = str(self.current_layer_issue.get("action_key") or "").strip()
        if not action_key:
            return
        self._log_gui_action("dashboard_repair", action=action_key)
        if action_key == "run_self_check":
            self._run_self_check()
            return
        if action_key == "repair_orchestrator" and self.runtime is not None:
            self.hero_var.set("后台准备中")
            self._dispatch("orchestrator_prepare", self.runtime.prepare_orchestrator_assets)
            return
        if action_key == "refresh_catalogs":
            self._refresh_knowledge_bases()
            self._refresh_expert_catalog()
            self.hero_var.set("系统已可用")
            return
        if action_key == "request_node_checks" and self.runtime is not None:
            self.runtime.request_remote_self_checks()
            self.hero_var.set("后台准备中")
            return

    def _fill_layer_cards(self, container: ttk.Frame | None, rows: List[tuple[str, str, str, str]], *, columns: int) -> None:
        if container is None:
            return
        for child in list(container.winfo_children()):
            child.destroy()
        total_columns = max(1, int(columns))
        for column in range(total_columns):
            container.columnconfigure(column, weight=1, uniform="layer-cards")
        for index, (layer_name, status_text, power_text, link_text) in enumerate(rows):
            row = index // total_columns
            column = index % total_columns
            card = ttk.Frame(container, style="Card.TFrame", padding=12)
            card.grid(row=row, column=column, sticky="nsew", padx=(0, 8 if column < total_columns - 1 else 0), pady=(0, 8))
            card.columnconfigure(0, weight=1)
            ttk.Label(card, text=layer_name, style="MetricLabel.TLabel").grid(row=0, column=0, sticky="w")
            normalized_status = str(status_text or "").strip()
            badge_color = "#20c997"
            if any(flag in normalized_status for flag in ("受限", "失败")):
                badge_color = "#f06a6a"
            elif any(flag in normalized_status for flag in ("准备", "连接", "自检", "部分")):
                badge_color = "#f6c344"
            tk.Label(
                card,
                text=normalized_status,
                bg=badge_color,
                fg="#0f1720",
                font=("Microsoft YaHei UI", 9, "bold"),
                padx=10,
                pady=4,
            ).grid(row=1, column=0, sticky="w", pady=(8, 0))
            ttk.Label(card, text=f"能力：{power_text}", style="MetricValue.TLabel").grid(row=2, column=0, sticky="w", pady=(10, 0))
            link_label = ttk.Label(card, text=f"链路：{link_text}", style="Body.TLabel", justify="left")
            link_label.grid(row=3, column=0, sticky="ew", pady=(8, 0))
            self._register_adaptive_wrap_label(link_label, card, padding=24, min_width=220, max_width=420)

    def _build_layer_rows(self, state: Dict[str, Any]) -> tuple[List[tuple[str, str, str, str]], List[tuple[str, str, str, str]]]:
        summary = dict(state.get("summary") or {})
        session = dict(state.get("session") or {})
        orchestrator_state = dict(state.get("orchestrator") or {})
        tasks = dict(state.get("tasks") or {})
        self_check = list(state.get("self_check") or [])
        streams = list(state.get("streams") or [])

        total_checks = max(1, len(self_check))
        passed_checks = sum(1 for row in self_check if str(row.get("status") or "").lower() == "pass")
        check_ratio = int((passed_checks / total_checks) * 100)
        local_task = dict(tasks.get("local") or {})
        node_tasks = dict(tasks.get("nodes") or {})
        online_nodes = int(summary.get("online_nodes", 0) or 0)
        offline_nodes = int(summary.get("offline_nodes", 0) or 0)
        expected_nodes = max(1, int(session.get("expected_nodes") or 1))

        orchestrator_status = str(orchestrator_state.get("status") or "not_installed").lower()
        planner_backend = str(orchestrator_state.get("planner_backend") or "deterministic").lower()
        if orchestrator_status == "ready":
            planner_ready = ("已就绪", "100%", "本机编排链已连通")
        elif orchestrator_status == "download_failed":
            planner_ready = ("受限", "72%", "已回退规则链")
        else:
            planner_ready = ("准备中", "82%", "后台准备中")

        knowledge_ready = bool(self.knowledge_catalog)
        expert_ready = bool(self.expert_catalog)
        selected_model = str(session.get("selected_model") or "").strip()
        execution_score = 70
        if selected_model:
            execution_score += 10
        if knowledge_ready:
            execution_score += 10
        if expert_ready:
            execution_score += 10
        execution_state = "已就绪" if execution_score >= 90 else "部分就绪"
        execution_link = "知识与专家链已连通" if knowledge_ready and expert_ready else "知识或专家目录待刷新"

        local_stage = str(local_task.get("stage") or "").strip()
        local_status = str(local_task.get("status") or "").lower()
        runtime_state = "已就绪"
        runtime_link = "本机运行链通畅"
        runtime_percent = f"{max(check_ratio, 100 if not self_check else 60)}%"
        if local_status == "running":
            runtime_state = "自检中"
            runtime_link = str(local_task.get("detail") or local_task.get("title") or "正在检查本机能力").strip()
            runtime_percent = f"{int(local_task.get('percent', 0) or 0)}%"
        elif local_status == "error":
            runtime_state = "受限"
            runtime_link = str(local_task.get("detail") or "本机自动补全未完成").strip()
            runtime_percent = f"{int(local_task.get('percent', 0) or 0)}%"
        elif local_stage:
            runtime_link = str(local_task.get("detail") or runtime_link).strip()

        pc_rows = [
            ("交互与展示层", "已就绪", "100%", "仪表盘界面已加载"),
            ("会话与服务层", runtime_state, runtime_percent, runtime_link),
            ("管家编排层", planner_ready[0], planner_ready[1], planner_ready[2]),
            ("执行与知识层", execution_state, f"{execution_score}%", execution_link),
        ]

        node_ratio = min(100, int((online_nodes / expected_nodes) * 100)) if expected_nodes else 0
        comm_state = "已连通" if online_nodes > 0 else ("连接中" if node_tasks else "待连接")
        comm_link = f"在线 {online_nodes} / 预期 {expected_nodes}"
        if offline_nodes > 0 and online_nodes > 0:
            comm_link = f"在线 {online_nodes} / 离线 {offline_nodes}"
        if not streams and not node_tasks:
            comm_link = "等待节点上线"

        pi_score = 20
        if online_nodes > 0:
            pi_score += 40
        if streams:
            pi_score += 20
        if any(str(item.get("status") or "").lower() == "success" for item in node_tasks.values()):
            pi_score += 20
        pi_state = "已就绪" if pi_score >= 80 else ("部分就绪" if pi_score >= 40 else "待连接")
        pi_link = "语音、播报与边缘事件链可用" if online_nodes > 0 else "等待 Pi 侧上线"

        pi_rows = [
            ("通信与节点管理层", comm_state, f"{node_ratio}%", comm_link),
            ("Pi 轻前端边缘层", pi_state, f"{pi_score}%", pi_link),
        ]
        return pc_rows, pi_rows

    def _format_orchestrator_status(self, status: str) -> str:
        return _present_orchestrator_status(status)

    def _format_planner_backend(self, backend: str) -> str:
        normalized = backend.strip().lower()
        return {
            "embedded_model": "内嵌模型",
            "deterministic": "规则链",
        }.get(normalized, "规则链" if not normalized else backend)

    def _render_checks(self, checks: List[Dict[str, Any]]) -> None:
        if self.check_tree is None:
            return
        self.check_tree.delete(*self.check_tree.get_children())
        for item in checks:
            self.check_tree.insert("", "end", values=(item.get("status", "-"), item.get("summary", "")))

    def _render_task_progress(self, task_state: Dict[str, Any]) -> None:
        local_task = dict((task_state or {}).get("local") or {})
        node_tasks = dict((task_state or {}).get("nodes") or {})
        progress_rows: List[Dict[str, str]] = []
        local_item = _build_task_progress_log_item(
            scope_label="本机任务",
            task=local_task,
            empty_title="本机当前无任务",
            empty_detail="等待系统自检、自动补全或后台准备。",
        )
        if local_item is not None:
            progress_rows.append(local_item)

        ordered_ids = sorted(node_tasks.keys(), key=lambda value: int(value) if str(value).isdigit() else str(value))
        for node_id in ordered_ids:
            item = _build_task_progress_log_item(
                scope_label=f"节点 {node_id}",
                task=node_tasks.get(node_id),
                empty_title=f"节点 {node_id} 当前无任务",
                empty_detail="等待节点发起自检或安装。",
            )
            if item is not None:
                progress_rows.append(item)
        self.task_progress_rows = progress_rows

    def _normalize_log_entry(self, row: Dict[str, Any]) -> Dict[str, str] | None:
        raw_text = str(row.get("rendered") or row.get("text") or "").strip()
        if not raw_text or re.fullmatch(r"[=\-]{8,}", raw_text):
            return None
        timestamp = str(row.get("timestamp") or "--:--:--")
        level = str(row.get("level") or "INFO").upper()
        text = raw_text
        match = re.match(r"^\[(INFO|WARN|WARNING|ERROR|SUCCESS)\]\s*(.*)$", raw_text, re.I)
        if match:
            level = match.group(1).upper()
            text = match.group(2).strip() or raw_text
        lowered = text.lower()
        category, summary = _classify_log_entry(text, level, lowered)
        if len(summary) > 120:
            summary = summary[:117].rstrip() + "..."
        detail = f"时间：{timestamp}\n级别：{level}\n模块：{category}\n内容：{text}"
        return {"key": f"{timestamp}|{level}|{category}|{text}", "time": timestamp, "level": level, "category": category, "summary": summary, "detail": detail}

    def _append_log_row(self, item: Dict[str, str]) -> None:
        if self.log_tree is None:
            return
        iid = f"log-{len(self.log_rows)}"
        self.log_rows.append(item)
        display_category = _present_log_category(item.get("category", ""))
        self.log_tree.insert("", "end", iid=iid, values=(item["time"], item["level"], display_category, item["summary"]), tags=(item["level"],))

    def _set_log_detail(self, detail: str) -> None:
        if self.log_detail_text is None:
            return
        self.log_detail_text.configure(state="normal")
        self.log_detail_text.delete("1.0", tk.END)
        self.log_detail_text.insert("1.0", detail)
        self.log_detail_text.configure(state="disabled")

    def _render_node_logs(self, recent: List[Dict[str, str]], streams: List[Dict[str, Any]] | None = None) -> None:
        if self.node_log_panel is None:
            return
        grouped: Dict[str, Dict[str, str]] = {}
        stream_rows = list(streams or [])
        if stream_rows:
            for item in stream_rows:
                node_id = str(item.get("id") or "").strip() or "0"
                grouped[node_id] = {
                    "connection": "已连接" if str(item.get("status") or "").lower() == "online" else "待连接",
                    "recognition": str(item.get("hint") or item.get("subtitle") or "等待识别结果").strip() or "等待识别结果",
                    "alert": str(item.get("hint") or item.get("subtitle") or "当前无告警").strip() or "当前无告警",
                }
        for item in recent:
            category = str(item.get("category", "")).strip()
            summary = str(item.get("summary", "")).strip()
            match = re.match(r"^节点\s+(\d+)\s+", summary)
            if not match:
                continue
            node_id = match.group(1)
            entry = grouped.setdefault(
                node_id,
                {
                    "connection": "待连接",
                    "recognition": "等待识别结果",
                    "alert": "当前无告警",
                },
            )
            if category == "节点通信":
                entry["connection"] = "已连接" if "握手成功" in summary or "在线" in summary else entry["connection"]
            elif category == "节点语音":
                entry["recognition"] = summary
            elif category == "节点播报":
                entry["alert"] = summary
            elif any(keyword in summary for keyword in ("高危", "告警", "报警", "泄漏", "火焰", "烟雾", "危化")):
                entry["alert"] = summary

        for child in list(self.node_log_panel.winfo_children()):
            if child not in {self.node_logs_title, self.node_log_empty_label}:
                child.destroy()

        if not grouped:
            if self.node_log_empty_label is not None:
                self.node_log_empty_label.configure(text="等待节点连接或节点状态更新。")
                self.node_log_empty_label.grid()
            if self.node_log_canvas is not None:
                self.node_log_canvas.configure(scrollregion=self.node_log_canvas.bbox("all"))
            return

        if self.node_log_empty_label is not None:
            self.node_log_empty_label.grid_remove()

        ordered_ids = sorted(grouped.keys(), key=lambda value: int(value) if str(value).isdigit() else str(value))
        total_columns = max(1, min(2, len(ordered_ids)))
        for column in range(total_columns):
            self.node_log_panel.columnconfigure(column, weight=1, uniform="node-state")

        for index, node_id in enumerate(ordered_ids):
            row = index // total_columns + 1
            column = index % total_columns
            latest = grouped[node_id]
            card = ttk.Frame(self.node_log_panel, style="Card.TFrame", padding=10)
            card.grid(row=row, column=column, sticky="nsew", padx=(0 if column == 0 else 8, 0), pady=(8, 0))
            card.columnconfigure(0, weight=1)
            ttk.Label(card, text=f"节点 {node_id}", style="MetricLabel.TLabel").grid(row=0, column=0, sticky="w")
            ttk.Label(card, text=f"连接：{latest['connection']}", style="PanelTitle.TLabel").grid(row=1, column=0, sticky="w", pady=(6, 0))
            recognition_label = ttk.Label(card, text=f"识别：{latest['recognition']}", style="CardBody.TLabel", justify="left")
            recognition_label.grid(row=2, column=0, sticky="ew", pady=(6, 0))
            alert_label = ttk.Label(card, text=f"告警：{latest['alert']}", style="CardBody.TLabel", justify="left")
            alert_label.grid(row=3, column=0, sticky="ew", pady=(6, 0))
            self._register_adaptive_wrap_label(recognition_label, card, padding=20, min_width=220, max_width=420)
            self._register_adaptive_wrap_label(alert_label, card, padding=20, min_width=220, max_width=420)
        if self.node_log_canvas is not None:
            self.node_log_canvas.configure(scrollregion=self.node_log_canvas.bbox("all"))

    def _on_log_tree_select(self, _event: tk.Event | None = None) -> None:
        if self.log_tree is None:
            return
        selection = self.log_tree.selection()
        if not selection:
            if self.log_rows:
                self._set_log_detail(self.log_rows[-1]["detail"])
            return
        iid = selection[0]
        if iid.startswith("log-"):
            index = int(iid.split("-", 1)[1])
            if 0 <= index < len(self.log_rows):
                self._set_log_detail(self.log_rows[index]["detail"])

    def _on_log_filter_changed(self, _event: tk.Event | None = None) -> None:
        if self.runtime is None:
            return
        try:
            self._render_logs(self.runtime.get_state().get("logs", []))
        except Exception:
            return

    def _render_logs(self, logs: List[Dict[str, Any]]) -> None:
        if self.log_tree is None:
            return
        recent = [item for item in (self._normalize_log_entry(row) for row in logs[-160:]) if item is not None]
        suppressed_categories = {"任务进度", "启动自检", "运行状态"}
        selected_filter = str(self.log_filter_var.get() or LOG_FILTER_OPTIONS[0]).strip() or LOG_FILTER_OPTIONS[0]
        system_recent = [
            item
            for item in recent
            if not str(item.get("category", "")).startswith("节点")
            and str(item.get("category", "")) not in suppressed_categories
        ]
        priority_item = _select_latest_priority_event(system_recent)
        priority_title, priority_detail = _format_priority_event_card(priority_item)
        self.priority_event_title_var.set(priority_title)
        self.priority_event_detail_var.set("")
        filtered_recent = [item for item in system_recent if _matches_log_filter(item, selected_filter)]
        display_recent = filtered_recent[-160:]
        keys = [item["key"] for item in display_recent]
        try:
            was_at_bottom = self.log_tree.yview()[1] >= 0.97
        except Exception:
            was_at_bottom = True
        if len(keys) >= len(self.log_row_keys) and keys[: len(self.log_row_keys)] == self.log_row_keys:
            for item in display_recent[len(self.log_row_keys):]:
                self._append_log_row(item)
        elif keys != self.log_row_keys:
            self.log_tree.delete(*self.log_tree.get_children())
            self.log_rows = []
            for item in display_recent:
                self._append_log_row(item)
        self.log_row_keys = keys
        if display_recent:
            latest = display_recent[-1]
            filter_text = "" if selected_filter == "全部" else f" | 筛选：{selected_filter}"
            self.log_status_var.set(f"最近事件 {len(display_recent)} 条{filter_text} | 最新：{latest['category']} / {latest['level']}")
            if was_at_bottom and self.log_rows:
                self.log_tree.see(f"log-{len(self.log_rows) - 1}")
            if not self.log_tree.selection():
                self._set_log_detail(latest["detail"])
        else:
            if selected_filter == "全部":
                self.log_status_var.set("等待运行数据")
                self._set_log_detail("当前还没有可展示的系统事件。")
            else:
                self.log_status_var.set(f"当前筛选：{selected_filter}，暂无匹配事件")
                self._set_log_detail(f"当前筛选：{selected_filter}\n暂无匹配事件。")
        self._render_node_logs(recent, self.current_state.get("streams", []))

    def _effective_left_width(self) -> int:
        return 0

    def _compute_stream_layout(self, stream_count: int) -> tuple[int, int, int]:
        wall_width = int(self.wall_canvas.winfo_width() or 0) if self.wall_canvas is not None else 0
        available_width = max(wall_width - 32, self.window_width - 160)
        if stream_count <= 1:
            columns = 1
        elif stream_count >= 3 and available_width >= 1650:
            columns = 3
        elif available_width >= 860:
            columns = 2
        else:
            columns = 1
        preview_width = int((available_width - (columns - 1) * 16 - 24) / columns)
        preview_width = max(420, min(720, preview_width))
        preview_height = max(236, int(preview_width * 9 / 16))
        return columns, preview_width, preview_height

    def _compute_text_limit(self, width: int, density: float, minimum: int, maximum: int) -> int:
        estimate = int(width / density)
        return max(minimum, min(maximum, estimate))

    def _truncate_text(self, text: str, limit: int) -> str:
        if len(text) <= limit:
            return text
        return text[: max(1, limit - 3)].rstrip() + "..."

    def _apply_stream_text(self, card: Dict[str, Any], stream: Dict[str, Any]) -> None:
        raw_title = str(stream.get("title") or "节点")
        title_text = raw_title.split("|", 1)[0].strip() or "节点"
        hint_text = stream.get("hint") or "等待状态更新"
        meta_text = stream["address"]
        title_limit = self._compute_text_limit(self.stream_preview_width, 10.0, 26, 70)
        body_limit = self._compute_text_limit(self.stream_preview_width, 7.2, 38, 120)
        meta_limit = self._compute_text_limit(self.stream_preview_width, 6.5, 44, 150)
        card["title"].set(self._truncate_text(title_text, title_limit))
        card["hint"].set(self._truncate_text(hint_text, body_limit))
        card["meta"].set(self._truncate_text(meta_text, meta_limit))
        self._set_tooltip_text(card["title_label"], title_text)
        self._set_tooltip_text(card["hint_label"], hint_text)
        self._set_tooltip_text(card["meta_label"], meta_text)
        badge_color = {
            "online": "#20c997",
            "connecting": "#f6c344",
            "offline": "#f06a6a",
        }.get(stream["status"], "#8899aa")
        card["status"].set(stream["status"].upper())
        card["status_label"].configure(bg=badge_color)

    def _refresh_stream_image(self, stream_id: str, card: Dict[str, Any], frame: Any | None = None) -> None:
        source = frame if frame is not None else self.stream_frame_cache.get(stream_id)
        if source is None:
            return
        resized = cv2.resize(source, (self.stream_preview_width, self.stream_preview_height))
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        image = Image.fromarray(rgb)
        photo = ImageTk.PhotoImage(image)
        card["image_label"].configure(image=photo, width=self.stream_preview_width, height=self.stream_preview_height)
        self.photo_refs[stream_id] = photo
        if self.stream_viewer_stream_id == stream_id:
            self._refresh_stream_viewer(stream_id, source)

    def _refresh_cached_stream_images(self) -> None:
        for stream_id, card in self.stream_cards.items():
            self._refresh_stream_image(stream_id, card)

    def _place_stream_card(self, card: Dict[str, Any], idx: int) -> None:
        row = idx // self.stream_columns
        column = idx % self.stream_columns
        card["frame"].grid(row=row, column=column, sticky="nsew", padx=8, pady=8)
        wraplength = max(260, self.stream_preview_width - 16)
        card["hint_label"].configure(wraplength=wraplength)
        card["meta_label"].configure(wraplength=wraplength)

    def _relayout_stream_cards(self, streams: List[Dict[str, Any]]) -> bool:
        if not streams:
            return False
        previous_layout = (self.stream_columns, self.stream_preview_width, self.stream_preview_height)
        self.stream_columns, self.stream_preview_width, self.stream_preview_height = self._compute_stream_layout(len(streams))
        for column in range(4):
            self.wall_inner.columnconfigure(column, weight=0, uniform="")
        for column in range(self.stream_columns):
            self.wall_inner.columnconfigure(column, weight=1, uniform="stream")
        for idx, stream in enumerate(streams):
            card = self.stream_cards.get(stream["id"])
            if card is not None:
                self._place_stream_card(card, idx)
        return previous_layout != (self.stream_columns, self.stream_preview_width, self.stream_preview_height)

    def _render_streams(self, streams: List[Dict[str, Any]]) -> None:
        if not streams:
            for child in list(self.wall_inner.winfo_children()):
                child.destroy()
            self.stream_cards.clear()
            self.stream_frame_cache.clear()
            self.stream_state_cache.clear()
            self._close_stream_viewer()
            placeholder = ttk.Label(self.wall_inner, text="尚未启动监控。配置完成后点击“启动监控”。", style="Body.TLabel")
            placeholder.grid(row=0, column=0, padx=12, pady=18, sticky="w")
            return

        if len(streams) and any(not isinstance(child, ttk.Frame) for child in self.wall_inner.winfo_children()):
            for child in list(self.wall_inner.winfo_children()):
                child.destroy()
            self.stream_cards.clear()

        self._relayout_stream_cards(streams)
        self.stream_state_cache = {stream["id"]: dict(stream) for stream in streams}
        existing_ids = set(self.stream_cards.keys())
        target_ids = {stream["id"] for stream in streams}
        for stale_id in existing_ids - target_ids:
            card = self.stream_cards.pop(stale_id)
            card["frame"].destroy()
            self.photo_refs.pop(stale_id, None)
            self.stream_frame_cache.pop(stale_id, None)
            self.stream_state_cache.pop(stale_id, None)
            if self.stream_viewer_stream_id == stale_id:
                self._close_stream_viewer()

        for idx, stream in enumerate(streams):
            card = self._ensure_stream_card(stream["id"])
            self._place_stream_card(card, idx)
            self._apply_stream_text(card, stream)
            frame = self.runtime._compose_frame(stream["id"])
            self.stream_frame_cache[stream["id"]] = frame
            self._refresh_stream_image(stream["id"], card, frame)

    def _ensure_stream_card(self, stream_id: str) -> Dict[str, Any]:
        if stream_id in self.stream_cards:
            return self.stream_cards[stream_id]

        frame = ttk.Frame(self.wall_inner, style="Card.TFrame", padding=12)
        frame.columnconfigure(0, weight=1)
        title_var = tk.StringVar(value=stream_id)
        status_var = tk.StringVar(value="offline")
        hint_var = tk.StringVar(value="等待状态更新")
        meta_var = tk.StringVar(value="")

        title_label = ttk.Label(frame, textvariable=title_var, style="PanelTitle.TLabel")
        title_label.grid(row=0, column=0, sticky="w")
        status_label = tk.Label(frame, textvariable=status_var, bg="#f6c344", fg="#0f1720", font=("Microsoft YaHei UI", 9, "bold"), padx=10, pady=4)
        status_label.grid(row=0, column=1, sticky="e")
        image_label = tk.Label(frame, bg="#101820")
        image_label.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(10, 10))
        hint_label = ttk.Label(frame, textvariable=hint_var, style="Body.TLabel", wraplength=self.stream_preview_width)
        hint_label.grid(row=2, column=0, columnspan=2, sticky="w")
        meta_label = ttk.Label(frame, textvariable=meta_var, style="Body.TLabel", wraplength=self.stream_preview_width)
        meta_label.grid(row=3, column=0, columnspan=2, sticky="w", pady=(8, 0))

        self._attach_tooltip(title_label)
        self._attach_tooltip(hint_label)
        self._attach_tooltip(meta_label)
        self._bind_stream_card(frame, stream_id)
        self._bind_stream_card(image_label, stream_id)
        self._bind_stream_card(title_label, stream_id)
        self._bind_stream_card(hint_label, stream_id)
        self._bind_stream_card(meta_label, stream_id)

        card = {
            "frame": frame,
            "title": title_var,
            "status": status_var,
            "hint": hint_var,
            "meta": meta_var,
            "status_label": status_label,
            "image_label": image_label,
            "title_label": title_label,
            "hint_label": hint_label,
            "meta_label": meta_label,
        }
        self.stream_cards[stream_id] = card
        return card

    def _bind_stream_card(self, widget: tk.Misc, stream_id: str) -> None:
        widget.bind("<Button-1>", lambda _event, sid=stream_id: self._open_stream_viewer(sid))
        try:
            widget.configure(cursor="hand2")
        except Exception:
            pass

    def _open_stream_viewer(self, stream_id: str) -> None:
        self.stream_viewer_stream_id = stream_id
        if self.stream_viewer_window is not None and self.stream_viewer_window.winfo_exists():
            self.stream_viewer_window.deiconify()
            self.stream_viewer_window.lift()
            self.stream_viewer_window.focus_force()
            self._refresh_stream_viewer(stream_id)
            return

        window = tk.Toplevel(self.root)
        window.title(f"{APP_DISPLAY_NAME} - 视频详情")
        self._set_window_geometry(window, min(1320, int(self.window_width * 0.78)), min(900, int(self.window_height * 0.82)), 960, 640)
        window.configure(bg="#0f1720")
        window.transient(self.root)
        self._apply_window_icon(window)
        self.window_refs.append(window)
        self.stream_viewer_window = window

        def _close_window() -> None:
            self._close_stream_viewer()

        window.protocol("WM_DELETE_WINDOW", _close_window)

        shell = ttk.Frame(window, style="Root.TFrame", padding=18)
        shell.pack(fill="both", expand=True)
        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(1, weight=1)

        header = ttk.Frame(shell, style="Panel.TFrame", padding=16)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, textvariable=self.stream_viewer_title_var, style="Header.TLabel").grid(row=0, column=0, sticky="w")
        stream_viewer_meta_label = ttk.Label(header, textvariable=self.stream_viewer_meta_var, style="Body.TLabel", justify="left")
        stream_viewer_meta_label.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        self._register_adaptive_wrap_label(stream_viewer_meta_label, header, padding=36, min_width=320, max_width=920)

        body = ttk.Frame(shell, style="Panel.TFrame", padding=16)
        body.grid(row=1, column=0, sticky="nsew", pady=(16, 0))
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)
        self.stream_viewer_label = tk.Label(body, bg="#101820")
        self.stream_viewer_label.grid(row=0, column=0, sticky="nsew")

        footer = ttk.Frame(shell, style="Panel.TFrame", padding=(10, 12))
        footer.grid(row=2, column=0, sticky="ew", pady=(16, 0))
        footer.columnconfigure(0, weight=1)
        stream_footer_label = ttk.Label(footer, text="点击右侧监控卡片可切换查看对象，画面将随实时流同步刷新。", style="Foot.TLabel", justify="left")
        stream_footer_label.grid(row=0, column=0, sticky="ew")
        self._register_adaptive_wrap_label(stream_footer_label, footer, padding=24, min_width=320, max_width=920)
        ttk.Button(footer, text="关闭", command=_close_window).grid(row=0, column=1, sticky="e")

        self._refresh_stream_viewer(stream_id)

    def _refresh_stream_viewer(self, stream_id: str, frame: Any | None = None) -> None:
        if self.stream_viewer_window is None or not self.stream_viewer_window.winfo_exists():
            return
        source = frame if frame is not None else self.stream_frame_cache.get(stream_id)
        if source is None or self.stream_viewer_label is None:
            return

        meta = self.stream_state_cache.get(stream_id, {})
        title = str(meta.get("title") or stream_id)
        subtitle = str(meta.get("subtitle") or "")
        hint = str(meta.get("hint") or "")
        address = str(meta.get("address") or "")
        self.stream_viewer_title_var.set(title)
        self.stream_viewer_meta_var.set(" | ".join(part for part in (address, subtitle, hint) if part))

        max_width = max(self.stream_viewer_window.winfo_width() - 80, 960)
        max_height = max(self.stream_viewer_window.winfo_height() - 220, 540)
        src_h, src_w = source.shape[:2]
        scale = min(max_width / max(src_w, 1), max_height / max(src_h, 1))
        width = max(640, int(src_w * scale))
        height = max(360, int(src_h * scale))
        resized = cv2.resize(source, (width, height))
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        photo = ImageTk.PhotoImage(Image.fromarray(rgb))
        self.stream_viewer_label.configure(image=photo, width=width, height=height)
        self.stream_viewer_photo = photo

    def _close_stream_viewer(self) -> None:
        window = self.stream_viewer_window
        self.stream_viewer_window = None
        self.stream_viewer_label = None
        self.stream_viewer_photo = None
        self.stream_viewer_stream_id = None
        self.stream_viewer_title_var.set("")
        self.stream_viewer_meta_var.set("")
        if window is not None:
            try:
                window.destroy()
            except Exception:
                pass

    def _read_document(self, path: Path, fallback: str) -> str:
        try:
            if path.exists():
                return path.read_text(encoding="utf-8")
        except Exception:
            pass
        return fallback

    def _prepare_markdown_tags(self, viewer: tk.Text) -> None:
        viewer.tag_configure("md_body", spacing1=2, spacing3=2)
        viewer.tag_configure("md_h1", font=("Microsoft YaHei UI", 16, "bold"), spacing1=8, spacing3=6)
        viewer.tag_configure("md_h2", font=("Microsoft YaHei UI", 13, "bold"), spacing1=8, spacing3=4)
        viewer.tag_configure("md_h3", font=("Microsoft YaHei UI", 11, "bold"), spacing1=6, spacing3=3)
        viewer.tag_configure("md_code", font=("Consolas", 10), background="#16212d", foreground="#e8f0f8", spacing1=2, spacing3=2)
        viewer.tag_configure("md_quote", foreground="#8fb3c9", lmargin1=18, lmargin2=18, spacing1=2, spacing3=2)

    def _normalize_markdown_inline(self, text: str) -> str:
        text = re.sub(r"!\[(.*?)\]\((.*?)\)", r"[image: \1]", text)
        text = re.sub(r"\[(.*?)\]\((.*?)\)", r"\1 (\2)", text)
        text = re.sub(r"`([^`]+)`", r"\1", text)
        text = text.replace("**", "")
        text = text.replace("__", "")
        return text

    def _render_markdown(self, viewer: tk.Text, body: str) -> None:
        viewer.configure(state="normal")
        viewer.delete("1.0", tk.END)
        self._prepare_markdown_tags(viewer)
        in_code = False
        for raw_line in body.splitlines():
            stripped = raw_line.strip()
            if stripped.startswith("```"):
                in_code = not in_code
                continue
            if in_code:
                viewer.insert(tk.END, f"{raw_line}\n", "md_code")
                continue
            if not stripped:
                viewer.insert(tk.END, "\n", "md_body")
                continue
            if stripped.startswith("### "):
                viewer.insert(tk.END, self._normalize_markdown_inline(stripped[4:]) + "\n", "md_h3")
                continue
            if stripped.startswith("## "):
                viewer.insert(tk.END, self._normalize_markdown_inline(stripped[3:]) + "\n", "md_h2")
                continue
            if stripped.startswith("# "):
                viewer.insert(tk.END, self._normalize_markdown_inline(stripped[2:]) + "\n", "md_h1")
                continue
            if stripped.startswith("> "):
                viewer.insert(tk.END, self._normalize_markdown_inline(stripped[2:]) + "\n", "md_quote")
                continue
            if re.match(r"^[-*]\s+", stripped):
                line = "- " + self._normalize_markdown_inline(re.sub(r"^[-*]\s+", "", stripped))
                viewer.insert(tk.END, line + "\n", "md_body")
                continue
            if re.match(r"^\d+\.\s+", stripped):
                viewer.insert(tk.END, self._normalize_markdown_inline(stripped) + "\n", "md_body")
                continue
            viewer.insert(tk.END, self._normalize_markdown_inline(raw_line) + "\n", "md_body")
        viewer.configure(state="disabled")

    def _show_about_and_copyright(self) -> None:
        self._show_about_window()

    def _show_about_window(self) -> None:
        self._log_gui_action("open_about_window")
        if self.about_window is not None and self.about_window.winfo_exists():
            self.about_window.deiconify()
            self.about_window.lift()
            self.about_window.focus_force()
            return
        window = tk.Toplevel(self.root)
        window.title(f"关于 {APP_DISPLAY_NAME}")
        self._set_window_geometry(window, 820, 560, 680, 480)
        window.configure(bg="#0f1720")
        window.transient(self.root)
        self._apply_window_icon(window)
        self.window_refs.append(window)
        self.about_window = window

        def _close_window() -> None:
            self.about_window = None
            window.destroy()

        window.protocol("WM_DELETE_WINDOW", _close_window)

        shell = ttk.Frame(window, style="Root.TFrame", padding=20)
        shell.pack(fill="both", expand=True)
        shell.columnconfigure(1, weight=1)

        logo = self._load_logo_image((128, 128))
        if logo is not None:
            label = tk.Label(shell, image=logo, bg="#0f1720")
            label.image = logo
            label.grid(row=0, column=0, rowspan=4, sticky="nw", padx=(0, 18))
        else:
            tk.Label(shell, text="LD", bg="#182330", fg="#78e6ff", font=("Bahnschrift", 34, "bold"), padx=28, pady=32).grid(row=0, column=0, rowspan=4, sticky="nw", padx=(0, 18))

        ttk.Label(shell, text=APP_DISPLAY_NAME, style="Header.TLabel").grid(row=0, column=1, sticky="w")
        ttk.Label(shell, text=APP_SHORT_TAGLINE, style="Brand.TLabel").grid(row=1, column=1, sticky="w", pady=(8, 0))
        ttk.Label(shell, text=f"版本 v{self.app_version} | {COMPANY_NAME}", style="Body.TLabel").grid(row=2, column=1, sticky="w", pady=(12, 0))
        description_label = ttk.Label(shell, text=APP_DESCRIPTION, style="Body.TLabel", justify="left")
        description_label.grid(row=3, column=1, sticky="ew", pady=(12, 0))
        self._register_adaptive_wrap_label(description_label, shell, padding=190, min_width=280, max_width=620)

        body = ttk.Frame(shell, style="Panel.TFrame", padding=18)
        body.grid(row=4, column=0, columnspan=2, sticky="nsew", pady=(20, 0))
        body.columnconfigure(0, weight=1)
        ttk.Label(body, text="核心能力", style="PanelTitle.TLabel").grid(row=0, column=0, sticky="w")
        feature_text = (
            "1. 桌面式运行配置与启动自检\n"
            "2. 本机与多节点并行监控墙\n"
            "3. 节点提示信息与运行日志统一展示\n"
            "4. 软件图标、版本资源、版权信息统一内置\n"
            "5. 适合软件著作权截图、演示与交付"
        )
        feature_label = ttk.Label(body, text=feature_text, style="Body.TLabel", justify="left")
        feature_label.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        self._register_adaptive_wrap_label(feature_label, body, padding=36, min_width=260, max_width=700)
        ttk.Button(body, text="关闭", command=window.destroy).grid(row=2, column=0, sticky="e", pady=(20, 0))

    def _show_copyright_window(self) -> None:
        fallback = f"{LEGAL_NOTICE}\n\n{COPYRIGHT_TEXT}"
        self._open_text_window(
            title="版权信息",
            heading="软件版权页",
            body=self._read_document(copyright_path(), fallback),
            size="820x620",
        )

    def _show_manual_window(self) -> None:
        self._log_gui_action("open_manual_window")
        fallback = (
            f"{APP_DISPLAY_NAME}\n\n"
            "这是内置的软件说明页面，用于展示软件用途、主要功能、运行方式和交付形态。\n"
            "如需完整说明，请查看 docs 目录中的说明文档。"
        )
        self._open_text_window(
            title="软件说明",
            heading="软件说明文档",
            body=self._read_document(manual_path(), fallback),
            size="900x700",
        )

    def _open_text_window(self, title: str, heading: str, body: str, size: str) -> None:
        window = tk.Toplevel(self.root)
        window.title(f"{APP_DISPLAY_NAME} - {title}")
        width, height = (int(part) for part in size.split("x", 1))
        self._set_window_geometry(window, width, height, min(640, width), min(480, height))
        window.configure(bg="#0f1720")
        window.transient(self.root)
        self._apply_window_icon(window)
        self.window_refs.append(window)

        shell = ttk.Frame(window, style="Root.TFrame", padding=18)
        shell.pack(fill="both", expand=True)
        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(1, weight=1)

        ttk.Label(shell, text=heading, style="Header.TLabel").grid(row=0, column=0, sticky="w")
        text_frame = ttk.Frame(shell, style="Panel.TFrame", padding=12)
        text_frame.grid(row=1, column=0, sticky="nsew", pady=(16, 0))
        text_frame.columnconfigure(0, weight=1)
        text_frame.rowconfigure(0, weight=1)

        viewer = tk.Text(text_frame, bg="#0f1720", fg="#dbe6f2", insertbackground="#dbe6f2", relief="flat", font=("Microsoft YaHei UI", 10), wrap="word")
        viewer.grid(row=0, column=0, sticky="nsew")
        self._render_markdown(viewer, body)
        scrollbar = ttk.Scrollbar(text_frame, orient="vertical", command=viewer.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        viewer.configure(yscrollcommand=scrollbar.set)
        self._register_scroll_target(text_frame, viewer)
        self._register_scroll_target(viewer, viewer)

        ttk.Button(shell, text="关闭", command=window.destroy).grid(row=2, column=0, sticky="e", pady=(16, 0))

    def _apply_window_icon(self, window: tk.Toplevel) -> None:
        try:
            ico = icon_path()
            if ico.exists():
                window.iconbitmap(default=str(ico))
        except Exception:
            pass
        if self.logo_image is not None:
            try:
                window.iconphoto(True, self.logo_image)
            except Exception:
                pass

    def _set_window_geometry(self, window: tk.Toplevel, width: int, height: int, min_width: int, min_height: int) -> None:
        max_width = max(560, self.screen_width - self._scaled(120))
        max_height = max(420, self.screen_height - self._scaled(140))
        actual_width = min(width, max_width)
        actual_height = min(height, max_height)
        offset_x = max(24, int((self.screen_width - actual_width) / 2))
        offset_y = max(24, int((self.screen_height - actual_height) / 2))
        window.geometry(f"{actual_width}x{actual_height}+{offset_x}+{offset_y}")
        window.minsize(min_width, min_height)

    def _sanitize_geometry(self, geometry: str) -> str | None:
        match = re.match(r"^\s*(\d+)x(\d+)([+-]\d+)([+-]\d+)\s*$", geometry)
        if match is None:
            return None
        width = min(max(int(match.group(1)), 1180), max(1180, self.screen_width - self._scaled(80)))
        height = min(max(int(match.group(2)), 820), max(820, self.screen_height - self._scaled(80)))
        x = int(match.group(3))
        y = int(match.group(4))
        max_x = max(0, self.screen_width - width)
        max_y = max(0, self.screen_height - height)
        x = min(max(x, 0), max_x)
        y = min(max(y, 0), max_y)
        return f"{width}x{height}+{x}+{y}"

    def _register_scroll_target(self, widget: Any, y_target: Any, x_target: Any | None = None) -> None:
        self.scroll_routes[str(widget)] = {"y": y_target, "x": x_target}

    def _resolve_scroll_target(self, widget: Any) -> Dict[str, Any] | None:
        current = widget
        while current is not None:
            route = self.scroll_routes.get(str(current))
            if route is not None:
                return route
            current = getattr(current, "master", None)
        return None

    def _bind_global_scroll_support(self) -> None:
        self.root.bind_all("<MouseWheel>", self._on_global_mousewheel, add="+")
        self.root.bind_all("<Shift-MouseWheel>", self._on_global_shift_mousewheel, add="+")
        self.root.bind_all("<Button-4>", lambda event: self._on_legacy_mousewheel(event, -1), add="+")
        self.root.bind_all("<Button-5>", lambda event: self._on_legacy_mousewheel(event, 1), add="+")

    def _pointer_widget(self) -> Any | None:
        try:
            return self.root.winfo_containing(self.root.winfo_pointerx(), self.root.winfo_pointery())
        except Exception:
            return None

    def _scroll_vertical(self, route: Dict[str, Any] | None, units: int) -> None:
        if route is None or units == 0:
            return
        target = route.get("y")
        if target is None:
            return
        try:
            target.yview_scroll(units, "units")
        except Exception:
            pass

    def _scroll_horizontal(self, route: Dict[str, Any] | None, units: int) -> None:
        if route is None or units == 0:
            return
        target = route.get("x") or route.get("y")
        if target is None:
            return
        try:
            target.xview_scroll(units, "units")
        except Exception:
            pass

    def _mousewheel_units(self, event: tk.Event) -> int:
        delta = getattr(event, "delta", 0)
        if delta == 0:
            return 0
        if delta > 0:
            return -1 * max(1, int(abs(delta) / 120))
        return max(1, int(abs(delta) / 120))

    def _on_global_mousewheel(self, event: tk.Event) -> None:
        route = self._resolve_scroll_target(self._pointer_widget())
        self._scroll_vertical(route, self._mousewheel_units(event))

    def _on_global_shift_mousewheel(self, event: tk.Event) -> None:
        route = self._resolve_scroll_target(self._pointer_widget())
        self._scroll_horizontal(route, self._mousewheel_units(event))

    def _on_legacy_mousewheel(self, _event: tk.Event, units: int) -> None:
        route = self._resolve_scroll_target(self._pointer_widget())
        self._scroll_vertical(route, units)

    def _set_tooltip_text(self, widget: Any, text: str) -> None:
        setattr(widget, "_tooltip_text", text)

    def _attach_tooltip(self, widget: Any) -> None:
        if getattr(widget, "_tooltip_bound", False):
            return
        setattr(widget, "_tooltip_bound", True)
        widget.bind("<Enter>", self._schedule_tooltip, add="+")
        widget.bind("<Leave>", self._hide_tooltip, add="+")
        widget.bind("<Motion>", self._move_tooltip, add="+")

    def _schedule_tooltip(self, event: tk.Event) -> None:
        self._hide_tooltip()
        text = getattr(event.widget, "_tooltip_text", "")
        if not text:
            return
        self.tooltip_after_id = self.root.after(360, lambda: self._show_tooltip(text))

    def _show_tooltip(self, text: str) -> None:
        self._hide_tooltip()
        tooltip = tk.Toplevel(self.root)
        tooltip.wm_overrideredirect(True)
        tooltip.attributes("-topmost", True)
        label = tk.Label(tooltip, text=text, justify="left", bg="#071018", fg="#f5f7fb", relief="solid", borderwidth=1, padx=10, pady=6, wraplength=480, font=("Microsoft YaHei UI", 9))
        label.pack()
        self.tooltip_window = tooltip
        self._position_tooltip()

    def _position_tooltip(self) -> None:
        if self.tooltip_window is None:
            return
        try:
            x = self.root.winfo_pointerx() + 18
            y = self.root.winfo_pointery() + 18
            self.tooltip_window.geometry(f"+{x}+{y}")
        except Exception:
            pass

    def _move_tooltip(self, _event: tk.Event) -> None:
        if self.tooltip_window is not None:
            self._position_tooltip()

    def _hide_tooltip(self, _event: tk.Event | None = None) -> None:
        if self.tooltip_after_id is not None:
            try:
                self.root.after_cancel(self.tooltip_after_id)
            except Exception:
                pass
            self.tooltip_after_id = None
        if self.tooltip_window is not None:
            try:
                self.tooltip_window.destroy()
            except Exception:
                pass
            self.tooltip_window = None

    def _schedule_window_state_save(self) -> None:
        if self.window_state_after_id is not None:
            try:
                self.root.after_cancel(self.window_state_after_id)
            except Exception:
                pass
        self.window_state_after_id = self.root.after(320, self._save_window_state)

    def _save_window_state(self) -> None:
        self.window_state_after_id = None
        try:
            geometry = self.root.geometry()
            state = self.root.state()
        except Exception:
            return
        set_config("desktop_ui.window_geometry", geometry)
        set_config("desktop_ui.window_state", state)
        set_config("desktop_ui.demo_mode", self.demo_mode_var.get())

    def _restore_window_state(self) -> None:
        geometry = str(get_config("desktop_ui.window_geometry", "") or "").strip()
        state = str(get_config("desktop_ui.window_state", "normal") or "normal").lower()
        demo_mode = bool(get_config("desktop_ui.demo_mode", False))
        if geometry:
            try:
                safe_geometry = self._sanitize_geometry(geometry)
                if safe_geometry is not None:
                    self.root.geometry(safe_geometry)
            except Exception:
                pass
        self.root.update_idletasks()
        if state == "zoomed" and not demo_mode:
            try:
                self.root.state("zoomed")
            except Exception:
                pass
        if demo_mode and self.hidden_demo_enabled:
            self._toggle_demo_mode(True, persist=False)
        self._refresh_responsive_layout()

    def _reset_window_layout(self) -> None:
        try:
            self.root.state("normal")
        except Exception:
            pass
        if self.demo_mode_var.get():
            self._toggle_demo_mode(False, persist=False)
        self._sync_monitor_metrics()
        self._configure_window_metrics()
        self._schedule_responsive_refresh()
        self._schedule_window_state_save()

    def _set_left_panel_collapsed(self, collapsed: bool, persist: bool = True) -> None:
        self.left_collapsed_var.set(False)
        if persist:
            self._schedule_window_state_save()

    def _toggle_left_panel(self) -> None:
        self._select_dashboard_tab("overview")

    def _toggle_demo_mode(self, enabled: bool | None = None, persist: bool = True) -> None:
        target = (not self.demo_mode_var.get()) if enabled is None else bool(enabled)
        if target and not self.hidden_demo_enabled:
            return
        if target == self.demo_mode_var.get():
            return
        if target:
            self.demo_restore_geometry = self.root.geometry()
            try:
                self.demo_restore_state = self.root.state()
            except Exception:
                self.demo_restore_state = "normal"
            self.demo_mode_var.set(True)
            try:
                self.root.state("zoomed")
            except Exception:
                try:
                    self.root.attributes("-fullscreen", True)
                except Exception:
                    pass
        else:
            self.demo_mode_var.set(False)
            try:
                self.root.attributes("-fullscreen", False)
            except Exception:
                pass
            try:
                self.root.state("normal")
            except Exception:
                pass
            if self.demo_restore_state == "zoomed":
                try:
                    self.root.state("zoomed")
                except Exception:
                    pass
            elif self.demo_restore_geometry:
                safe_geometry = self._sanitize_geometry(self.demo_restore_geometry)
                if safe_geometry is not None:
                    self.root.geometry(safe_geometry)
        self._update_session_badge()
        self._schedule_responsive_refresh()
        if persist:
            self._schedule_window_state_save()

    def _handle_escape_key(self) -> None:
        if self.demo_mode_var.get():
            self._toggle_demo_mode(False)

    def _sync_monitor_metrics(self) -> bool:
        self.screen_width = self.root.winfo_screenwidth()
        self.screen_height = self.root.winfo_screenheight()
        new_scale = self._detect_window_scale()
        scale_changed = abs(new_scale - self.display_scale) >= 0.05
        self.display_scale = new_scale
        if scale_changed:
            self._apply_tk_scaling(self.display_scale)
            self._build_style()
        return scale_changed

    def _schedule_responsive_refresh(self) -> None:
        if self.resize_after_id is not None:
            try:
                self.root.after_cancel(self.resize_after_id)
            except Exception:
                pass
        self.resize_after_id = self.root.after(120, self._refresh_responsive_layout)

    def _refresh_responsive_layout(self) -> None:
        self.resize_after_id = None
        current_width = max(self.root.winfo_width(), 1180)
        current_height = max(self.root.winfo_height(), 820)
        self.window_width = current_width
        self.window_height = current_height
        self.hero_wraplength = max(480, min(current_width - 220, 1120))
        self.info_wraplength = max(320, min(current_width - 220, 960))
        if self.hero_message_label is not None:
            self.hero_message_label.configure(wraplength=self.hero_wraplength)
        if self.info_description_label is not None:
            self.info_description_label.configure(wraplength=self.info_wraplength)
        if self.info_copyright_label is not None:
            self.info_copyright_label.configure(wraplength=self.info_wraplength)
        if self.check_tree is not None:
            status_width = max(78, min(96, int(max(current_width * 0.15, 320) * 0.2)))
            summary_width = max(220, min(560, current_width - status_width - 180))
            self.check_tree.column("status", width=status_width)
            self.check_tree.column("summary", width=summary_width)
        self._render_summary(self.current_state)
        layout_changed = self._relayout_stream_cards(self.current_state.get("streams", []))
        if layout_changed:
            self._refresh_cached_stream_images()

    def _on_left_inner_configure(self, _event: tk.Event) -> None:
        return

    def _on_left_canvas_configure(self, event: tk.Event) -> None:
        self._schedule_responsive_refresh()

    def _on_wall_configure(self, _event: tk.Event) -> None:
        if self.wall_canvas is not None:
            self.wall_canvas.configure(scrollregion=self.wall_canvas.bbox("all"))

    def _on_canvas_configure(self, event: tk.Event) -> None:
        if self.wall_canvas is not None and self.wall_window is not None:
            self.wall_canvas.itemconfigure(self.wall_window, width=event.width)

    def _on_log_canvas_configure(self, event: tk.Event) -> None:
        if self.log_canvas is None or self.log_content_window is None or self.log_content is None:
            return
        desired_height = max(event.height, self.log_content.winfo_reqheight())
        self.log_canvas.itemconfigure(self.log_content_window, width=event.width, height=desired_height)
        self.log_canvas.configure(scrollregion=self.log_canvas.bbox("all"))

    def _on_main_splitter_drag(self, _event: tk.Event) -> None:
        return

    def _on_node_log_canvas_configure(self, event: tk.Event) -> None:
        if self.node_log_canvas is None or self.node_log_window is None:
            return
        self.node_log_canvas.itemconfigure(self.node_log_window, width=event.width)
        self.node_log_canvas.configure(scrollregion=self.node_log_canvas.bbox("all"))

    def _target_log_section_height(self) -> int:
        return 260

    def _rebalance_main_splitter(self) -> None:
        return

    def _on_root_configure(self, event: tk.Event) -> None:
        if event.widget is not self.root:
            return
        scale_changed = self._sync_monitor_metrics()
        if scale_changed:
            self._schedule_responsive_refresh()
        self._schedule_responsive_refresh()
        self._schedule_window_state_save()

    def _select_dashboard_tab(self, key: str) -> None:
        if self.main_notebook is None:
            return
        target = self.dashboard_tab_map.get(key)
        if not target:
            return
        for index in range(self.main_notebook.index("end")):
            if str(self.main_notebook.tab(index, "text")) == target:
                self.main_notebook.select(index)
                return

    def _build_menu(self) -> None:
        menubar = tk.Menu(
            self.root,
            tearoff=False,
            bg="#182330",
            fg="#f5f7fb",
            activebackground="#20c997",
            activeforeground="#0f1720",
        )
        software_menu = tk.Menu(
            menubar,
            tearoff=False,
            bg="#182330",
            fg="#f5f7fb",
            activebackground="#20c997",
            activeforeground="#0f1720",
        )
        software_menu.add_command(label="总览面板", command=lambda: self._select_dashboard_tab("overview"))
        software_menu.add_command(label="知识中心", command=lambda: self._select_dashboard_tab("knowledge"))
        software_menu.add_command(label="专家中心", command=lambda: self._select_dashboard_tab("expert"))
        software_menu.add_command(label="模型配置", command=lambda: self._select_dashboard_tab("cloud"))
        software_menu.add_command(label="训练中心", command=lambda: self._select_dashboard_tab("training"))
        software_menu.add_command(label="档案中心", command=lambda: self._select_dashboard_tab("archive"))
        software_menu.add_separator()
        software_menu.add_command(label="运行启动自检", command=self._run_self_check)
        software_menu.add_command(label="刷新模型", command=self._refresh_models)
        software_menu.add_separator()
        software_menu.add_command(label="退出", command=self._on_close)

        view_menu = tk.Menu(
            menubar,
            tearoff=False,
            bg="#182330",
            fg="#f5f7fb",
            activebackground="#20c997",
            activeforeground="#0f1720",
        )
        view_menu.add_command(label="恢复默认布局", command=self._reset_window_layout)

        help_menu = tk.Menu(
            menubar,
            tearoff=False,
            bg="#182330",
            fg="#f5f7fb",
            activebackground="#20c997",
            activeforeground="#0f1720",
        )
        help_menu.add_command(label="软件说明", command=self._show_manual_window)
        help_menu.add_command(label="关于软件", command=self._show_about_window)
        help_menu.add_command(label="版权信息", command=self._show_copyright_window)

        menubar.add_cascade(label="软件", menu=software_menu)
        menubar.add_cascade(label="视图", menu=view_menu)
        menubar.add_cascade(label="帮助", menu=help_menu)
        self.root.configure(menu=menubar)

    def _load_bootstrap(self) -> None:
        self._set_startup_progress(10, "正在初始化运行环境", "环境检查", "即将执行环境检查并加载主控制台")
        self._dispatch("bootstrap", self._bootstrap_runtime)

    def _post_startup_progress(self, payload: Dict[str, Any]) -> None:
        self.ui_queue.put(("progress", "startup", payload))

    def _bootstrap_runtime(self) -> Dict[str, Any]:
        from pc.webui.runtime import LabDetectorRuntime

        self._post_startup_progress({
            "value": 14,
            "message": "正在初始化核心服务",
            "step": "核心服务",
            "detail": "正在创建主控制台运行环境并准备基础服务",
        })
        runtime = LabDetectorRuntime()
        self.runtime = runtime
        runtime.on_task_progress_changed = lambda payload: self.ui_queue.put(("progress", "task_progress_sync", payload))
        self.app_version = runtime.version
        self._post_startup_progress({
            "value": 36,
            "message": "正在执行启动自检",
            "step": "启动自检",
            "detail": "正在完成缺失检查、自动补全和主界面启动前的最后准备",
        })
        payload = runtime.bootstrap(include_self_check=not self.skip_startup_splash, include_catalogs=True)
        return {"payload": payload}

    def _register_voice_local_handler(self) -> None:
        if self.voice_local_handler_started:
            return
        self.voice_local_handler_started = True

        def _worker() -> None:
            try:
                from pc.voice.voice_interaction import set_voice_local_command_handler

                set_voice_local_command_handler(self._handle_voice_local_command)
                self.voice_local_handler_ready = True
                self._log_gui_action("voice_local_handler_ready")
            except Exception as exc:
                self._log_gui_action("voice_local_handler_failed", error=str(exc))

        threading.Thread(target=_worker, daemon=True, name="UI_voice_local_handler").start()

    def _execute_voice_local_intent(self, intent: str) -> tuple[str, str] | None:
        mapping = {
            "start_monitor": (self._start_session, "start_monitoring", "监控已启动"),
            "stop_monitor": (self._stop_session, "stop_monitoring", "监控已停止"),
            "run_self_check": (self._run_self_check, "query_system_status", "系统自检已发起"),
            "open_expert_center": (self._show_expert_window, "open_view", "已切换到专家中心"),
            "open_knowledge_center": (self._show_knowledge_base_window, "open_view", "已切换到知识中心"),
            "open_model_config": (self._show_cloud_backend_window, "open_view", "已切换到模型配置"),
            "open_training_center": (self._show_training_window, "open_view", "已切换到训练中心"),
            "open_manual": (self._show_manual_window, "open_view", "已切换到使用手册"),
            "open_about": (self._show_about_window, "open_view", "已切换到关于系统"),
            "toggle_sidebar": (lambda: self._select_dashboard_tab("overview"), "open_view", "已切换到总览"),
            "shutdown_app": (self._on_close, "shutdown_app", "正在关闭软件"),
        }
        target = mapping.get(intent)
        if target is None:
            return None
        action, action_display, result_text = target
        if intent == "open_training_center":
            action("")
        else:
            action()
        return action_display, result_text

    def _handle_voice_local_command(self, _command_text: str, intent: str) -> str | None:
        mapping = {
            "start_monitor": "好的，正在启动监控。",
            "stop_monitor": "好的，正在停止监控。",
            "run_self_check": "好的，正在执行系统自检。",
            "open_expert_center": "好的，正在打开专家中心。",
            "open_knowledge_center": "好的，正在打开知识中心。",
            "open_model_config": "好的，正在打开模型配置。",
            "open_training_center": "好的，正在打开训练中心。",
            "open_manual": "好的，正在打开使用手册。",
            "open_about": "好的，正在打开关于系统。",
            "toggle_sidebar": "好的，正在切换到总览。",
            "shutdown_app": "好的，正在关闭软件。",
        }
        response = mapping.get(intent)
        if response is None:
            return None
        self.ui_queue.put(("ok", "voice_local_action", {"intent": intent}))
        return response

    def _apply_bootstrap_payload(self, payload: Dict[str, Any]) -> None:
        controls = payload["controls"]
        visible_backends = self._visible_backend_rows(controls["backends"])
        self.backend_combo["values"] = [item["label"] for item in visible_backends]
        self.backend_map = {item["label"]: item["value"] for item in visible_backends}
        self.backend_reverse = {value: label for label, value in self.backend_map.items()}
        self.mode_combo["values"] = [item["label"] for item in controls["modes"]]
        self.mode_map = {item["label"]: item["value"] for item in controls["modes"]}
        self.mode_reverse = {value: label for label, value in self.mode_map.items()}
        self.model_catalog = controls["models"]
        if "knowledge_bases" in payload:
            self.knowledge_catalog = payload.get("knowledge_bases", [])
        if "experts" in payload:
            self.expert_catalog = payload.get("experts", [])
        if "cloud_backends" in payload:
            self.cloud_backend_catalog = self._configurable_backend_rows(payload.get("cloud_backends", []))
        self._load_custom_model_registry()
        if "training" in payload:
            self.training_overview = payload.get("training", {})
        self._sync_knowledge_scope_choices()
        self._register_voice_local_handler()

        self.backend_var.set(controls["defaults"]["ai_backend"])
        self.mode_var.set(controls["defaults"]["mode"])
        self.backend_combo.set(self.backend_reverse.get(self.backend_var.get(), self.backend_combo.get()))
        self.mode_combo.set(self.mode_reverse.get(self.mode_var.get(), self.mode_combo.get()))
        self.expected_nodes_var.set(str(controls["defaults"]["expected_nodes"]))
        self.expected_entry.delete(0, tk.END)
        self.expected_entry.insert(0, self.expected_nodes_var.get())
        if self.project_entry is not None:
            self.project_entry.delete(0, tk.END)
            self.project_entry.insert(0, str(controls["defaults"].get("project_name", "")))
        if self.experiment_entry is not None:
            self.experiment_entry.delete(0, tk.END)
            self.experiment_entry.insert(0, str(controls["defaults"].get("experiment_name", "")))
        if self.operator_entry is not None:
            self.operator_entry.delete(0, tk.END)
            self.operator_entry.insert(0, str(controls["defaults"].get("operator_name", "")))
        if self.tags_entry is not None:
            self.tags_entry.delete(0, tk.END)
            self.tags_entry.insert(0, str(controls["defaults"].get("tags", "")))

        self._update_model_choices(controls["defaults"]["selected_model"])
        self.current_state = payload["state"]
        self._render_summary(payload["state"])
        self._render_checks(payload["state"]["self_check"])
        self._render_logs(payload["state"]["logs"])
        self._set_startup_progress(92, "正在完成主界面准备", "界面就绪", "正在同步运行状态、监控区域和系统事件")
        self._render_streams(payload["state"]["streams"])
        self._set_startup_progress(99, "正在启动工作台界面", "界面收尾", "正在挂载主工作台视图并完成启动前的最后准备")
        self.root.after(150, self._finish_startup)

    def _refresh_models(self) -> None:
        self._log_gui_action("click_refresh_model_catalog")
        self.hero_var.set("正在刷新模型")
        self._dispatch("refresh_models", self.runtime.refresh_model_catalog)
        self._dispatch("cloud_catalog", self.runtime.get_cloud_backend_catalog)

    def _refresh_knowledge_bases(self) -> None:
        self.hero_var.set("正在刷新知识库")
        self._dispatch("kb_catalog", self.runtime.get_knowledge_base_catalog)

    def _refresh_expert_catalog(self) -> None:
        self.hero_var.set("正在刷新专家")
        self._dispatch("expert_catalog", self.runtime.get_expert_catalog)

    def _refresh_cloud_backend_catalog(self) -> None:
        self.hero_var.set("正在刷新模型服务配置")
        self._dispatch("cloud_catalog", self.runtime.get_cloud_backend_catalog)

    def _sync_knowledge_scope_choices(self) -> None:
        labels: List[str] = []
        self.kb_scope_map = {}
        self.kb_scope_reverse = {}
        for row in self.knowledge_catalog:
            label = f"{row['title']} [{row['scope']}]"
            labels.append(label)
            self.kb_scope_map[label] = row["scope"]
            self.kb_scope_reverse[row["scope"]] = label
        if not labels:
            labels = ["公共背景知识库 [common]"]
            self.kb_scope_map = {labels[0]: "common"}
            self.kb_scope_reverse = {"common": labels[0]}
        if self.kb_scope_combo is not None:
            try:
                if not self.kb_scope_combo.winfo_exists():
                    return
            except Exception:
                return
            self.kb_scope_combo["values"] = labels
            if not self.kb_scope_combo.get():
                self.kb_scope_combo.set(labels[0])

    def _selected_expert_row(self) -> Dict[str, Any] | None:
        if self.expert_tree is None:
            return None
        selection = self.expert_tree.selection()
        if not selection:
            return None
        code = selection[0]
        for row in self.expert_catalog:
            if row["expert_code"] == code:
                return row
        return None

    def _dispatch_knowledge_import(self, paths: List[str], scope_name: str) -> None:
        if not paths:
            return
        normalized_paths = list(paths)
        reset_index = bool(self.kb_reset_var.get())
        structured = bool(self.kb_structured_var.get())
        self.kb_status_var.set("等待导入知识库")
        self.hero_var.set("正在刷新实验档案")
        self._dispatch(
            "kb_import",
            lambda: self.runtime.import_knowledge_paths(
                normalized_paths,
                scope_name=scope_name,
                reset_index=reset_index,
                structured=structured,
            ),
        )

    def _import_knowledge_files(self, scope_name: str | None = None) -> None:
        paths = filedialog.askopenfilenames(
            parent=self.kb_window or self.expert_window or self.root,
            title="选择要导入的文本 / 表格知识文件",
            filetypes=[
                ("Knowledge Files", "*.txt *.md *.csv *.json *.xls *.xlsx"),
                ("Text Files", "*.txt *.md"),
                ("Table Files", "*.csv *.xls *.xlsx"),
                ("JSON Files", "*.json"),
                ("All Files", "*.*"),
            ],
        )
        if paths:
            self._dispatch_knowledge_import(list(paths), scope_name or self._selected_kb_scope())

    def _import_knowledge_media_files(self, scope_name: str | None = None) -> None:
        paths = filedialog.askopenfilenames(
            parent=self.kb_window or self.expert_window or self.root,
            title="选择要导入的语音 / 视频 / 图片知识素材",
            filetypes=[
                ("Media Files", "*.wav *.mp3 *.m4a *.aac *.flac *.ogg *.mp4 *.avi *.mov *.mkv *.wmv *.webm *.jpg *.jpeg *.png *.bmp *.webp"),
                ("Audio Files", "*.wav *.mp3 *.m4a *.aac *.flac *.ogg"),
                ("Video Files", "*.mp4 *.avi *.mov *.mkv *.wmv *.webm"),
                ("Image Files", "*.jpg *.jpeg *.png *.bmp *.webp"),
                ("All Files", "*.*"),
            ],
        )
        if paths:
            self._dispatch_knowledge_import(list(paths), scope_name or self._selected_kb_scope())

    def _import_knowledge_folder(self, scope_name: str | None = None) -> None:
        directory = filedialog.askdirectory(
            parent=self.kb_window or self.expert_window or self.root,
            title="选择知识库文件夹",
        )
        if directory:
            self._dispatch_knowledge_import([directory], scope_name or self._selected_kb_scope())

    def _render_kb_detail(self, row: Dict[str, Any]) -> None:
        if self.kb_detail_text is None:
            return
        try:
            if not self.kb_detail_text.winfo_exists():
                return
        except Exception:
            return
        docs = row.get("docs") or []
        lines = [
            f"作用域: {row.get('scope', '')}",
            f"名称: {row.get('title', '')}",
            f"文档数量: {row.get('doc_count', 0)}",
            f"向量索引: {'已就绪' if row.get('vector_ready') else '轻量模式 / 未启用'}",
            f"结构化知识库: {'已就绪' if row.get('structured_ready') else '待导入'}",
            f"文档位置: {row.get('docs_dir', '')}",
            f"向量位置: {row.get('vector_path', '')}",
            f"结构化库路径: {row.get('structured_path', '')}",
            "",
            "当前收录文件:",
        ]
        if docs:
            lines.extend(f"- {name}" for name in docs)
        else:
            lines.append("- 暂无已导入文件")
        self.kb_detail_text.configure(state="normal")
        self.kb_detail_text.delete("1.0", tk.END)
        self.kb_detail_text.insert("1.0", "\n".join(lines))
        self.kb_detail_text.configure(state="disabled")

    def _on_kb_tree_select(self, _event: tk.Event | None = None) -> None:
        if self.kb_tree is None:
            return
        selection = self.kb_tree.selection()
        if not selection:
            return
        scope = selection[0]
        for row in self.knowledge_catalog:
            if row["scope"] == scope:
                self._render_kb_detail(row)
                break

    def _populate_knowledge_tree(self) -> None:
        if self.kb_tree is None:
            return
        try:
            if not self.kb_tree.winfo_exists():
                return
        except Exception:
            return
        self.kb_tree.delete(*self.kb_tree.get_children())
        for row in self.knowledge_catalog:
            self.kb_tree.insert(
                "",
                "end",
                iid=row["scope"],
                values=(
                    row["scope"],
                    row["title"],
                    row.get("doc_count", 0),
                    "已启用" if row.get("vector_ready") else "轻量模式",
                    "已就绪" if row.get("structured_ready") else "待导入",
                ),
            )
        if self.knowledge_catalog:
            first_scope = self.knowledge_catalog[0]["scope"]
            self.kb_tree.selection_set(first_scope)
            self._render_kb_detail(self.knowledge_catalog[0])
            if self.kb_scope_combo is not None:
                self.kb_scope_combo.set(self.kb_scope_reverse.get(first_scope, self.kb_scope_combo.get()))

    def _show_knowledge_base_window(self) -> None:
        self._log_gui_action("open_knowledge_base_window")
        self._select_dashboard_tab("knowledge")
        self._refresh_knowledge_bases()
        return

        window = tk.Toplevel(self.root)
        window.title(f"{APP_DISPLAY_NAME} - 知识库管理")
        self._set_window_geometry(window, min(1220, int(self.window_width * 0.76)), min(840, int(self.window_height * 0.82)), 920, 640)
        window.configure(bg="#0f1720")
        window.transient(self.root)
        self._apply_window_icon(window)
        self.window_refs.append(window)
        self.kb_window = window

        def _close_window() -> None:
            self.kb_window = None
            window.destroy()

        window.protocol("WM_DELETE_WINDOW", _close_window)

        shell = ttk.Frame(window, style="Root.TFrame", padding=18)
        shell.pack(fill="both", expand=True)
        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(1, weight=1)

        header = ttk.Frame(shell, style="Panel.TFrame", padding=16)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="多知识库管理", style="Header.TLabel").grid(row=0, column=0, sticky="w")
        kb_header_hint = ttk.Label(
            header,
            text="支持公共背景知识库与专家专属知识库；文本、语音、视频、图片都可一键导入。",
            style="Body.TLabel",
            justify="left",
        )
        kb_header_hint.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        self._register_adaptive_wrap_label(kb_header_hint, header, padding=36, min_width=320, max_width=920)

        control = ttk.Frame(shell, style="Panel.TFrame", padding=16)
        control.grid(row=1, column=0, sticky="nsew", pady=(16, 0))
        control.columnconfigure(0, weight=3)
        control.columnconfigure(1, weight=2)
        control.rowconfigure(1, weight=1)

        topbar = ttk.Frame(control, style="SoftPanel.TFrame", padding=12)
        topbar.grid(row=0, column=0, columnspan=2, sticky="ew")
        topbar.columnconfigure(1, weight=1)
        topbar.columnconfigure(2, weight=1)
        ttk.Label(topbar, text="导入目标", style="Body.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 8))
        self.kb_scope_combo = ttk.Combobox(topbar, state="readonly")
        self.kb_scope_combo.grid(row=0, column=1, columnspan=2, sticky="ew", padx=(10, 0), pady=(0, 8))
        options_bar = ttk.Frame(topbar, style="SoftPanel.TFrame")
        options_bar.grid(row=1, column=0, columnspan=3, sticky="ew")
        options_bar.columnconfigure(0, weight=1)
        options_bar.columnconfigure(1, weight=1)
        ttk.Checkbutton(options_bar, text="导入前重建当前作用域索引", variable=self.kb_reset_var).grid(row=0, column=0, sticky="w", padx=(0, 12))
        ttk.Checkbutton(options_bar, text="同步写入结构化知识库", variable=self.kb_structured_var).grid(row=0, column=1, sticky="w")
        kb_action_bar = ttk.Frame(topbar, style="SoftPanel.TFrame")
        kb_action_bar.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(10, 0))
        self._grid_action_bar(
            kb_action_bar,
            [
                ttk.Button(kb_action_bar, text="导入文本 / 表格", command=self._import_knowledge_files),
                ttk.Button(kb_action_bar, text="导入语音 / 视频 / 图片", command=self._import_knowledge_media_files),
                ttk.Button(kb_action_bar, text="导入整个文件夹", command=self._import_knowledge_folder),
                ttk.Button(kb_action_bar, text="导入公共背景库", command=lambda: self._import_knowledge_files("common")),
                ttk.Button(kb_action_bar, text="刷新知识库", command=self._refresh_knowledge_bases),
            ],
            columns=3,
        )

        table_wrap = ttk.Frame(control, style="SoftPanel.TFrame", padding=12)
        table_wrap.grid(row=1, column=0, sticky="nsew", pady=(14, 0), padx=(0, 10))
        table_wrap.columnconfigure(0, weight=1)
        table_wrap.rowconfigure(0, weight=1)

        self.kb_tree = ttk.Treeview(table_wrap, columns=("scope", "title", "docs", "vector", "structured"), show="headings")
        self.kb_tree.heading("scope", text="作用域")
        self.kb_tree.heading("title", text="名称")
        self.kb_tree.heading("docs", text="文件数")
        self.kb_tree.heading("vector", text="索引状态")
        self.kb_tree.heading("structured", text="结构化库")
        self.kb_tree.column("scope", width=240, anchor="w")
        self.kb_tree.column("title", width=260, anchor="w")
        self.kb_tree.column("docs", width=80, anchor="center")
        self.kb_tree.column("vector", width=110, anchor="center")
        self.kb_tree.column("structured", width=110, anchor="center")
        self.kb_tree.grid(row=0, column=0, sticky="nsew")
        self.kb_tree.bind("<<TreeviewSelect>>", self._on_kb_tree_select)
        table_scroll = ttk.Scrollbar(table_wrap, orient="vertical", command=self.kb_tree.yview)
        table_scroll.grid(row=0, column=1, sticky="ns")
        self.kb_tree.configure(yscrollcommand=table_scroll.set)

        detail_wrap = ttk.Frame(control, style="SoftPanel.TFrame", padding=12)
        detail_wrap.grid(row=1, column=1, sticky="nsew", pady=(14, 0))
        detail_wrap.columnconfigure(0, weight=1)
        detail_wrap.rowconfigure(1, weight=1)
        ttk.Label(detail_wrap, text="作用域详情", style="PanelTitle.TLabel").grid(row=0, column=0, sticky="w")
        self.kb_detail_text = tk.Text(detail_wrap, bg="#0f1720", fg="#dbe6f2", insertbackground="#dbe6f2", relief="flat", font=("Microsoft YaHei UI", 10), wrap="word")
        self.kb_detail_text.grid(row=1, column=0, sticky="nsew", pady=(12, 0))
        self.kb_detail_text.configure(state="disabled")
        self._register_scroll_target(self.kb_tree, self.kb_tree)
        self._register_scroll_target(detail_wrap, self.kb_detail_text)
        self._register_scroll_target(self.kb_detail_text, self.kb_detail_text)

        footer = ttk.Frame(shell, style="Panel.TFrame", padding=(10, 12))
        footer.grid(row=2, column=0, sticky="ew", pady=(16, 0))
        footer.columnconfigure(0, weight=1)
        kb_status_label = ttk.Label(footer, textvariable=self.kb_status_var, style="Foot.TLabel", justify="left")
        kb_status_label.grid(row=0, column=0, sticky="ew")
        self._register_adaptive_wrap_label(kb_status_label, footer, padding=24, min_width=320, max_width=1080)
        ttk.Button(footer, text="关闭", command=_close_window).grid(row=0, column=1, sticky="e")

        self._sync_knowledge_scope_choices()
        if self.kb_scope_combo["values"]:
            self.kb_scope_combo.set(self.kb_scope_combo["values"][0])
        self._populate_knowledge_tree()
        self._refresh_knowledge_bases()

    def _render_expert_detail(self, row: Dict[str, Any]) -> None:
        if self.expert_detail_text is None:
            return
        try:
            if not self.expert_detail_text.winfo_exists():
                return
        except Exception:
            return
        lines = [
            f"专家名称: {row.get('display_name', '')}",
            f"专家编码: {row.get('expert_code', '')}",
            f"专家类别: {row.get('category', '')}",
            f"说明: {row.get('description', '')}",
            f"已加载到系统: {'是' if row.get('loaded') else '否'}",
            f"需要专家模型: {'是' if row.get('model_required') else '否'}",
            f"需要知识库: {'是' if row.get('knowledge_required') else '否'}",
            f"专家模型位置: {row.get('asset_path', '')}",
            f"专家模型文件数: {row.get('asset_file_count', 0)}",
            f"知识库作用域: {row.get('knowledge_scope', '')}",
            f"知识库文档数: {row.get('knowledge_doc_count', 0)}",
            f"建议素材类型: {', '.join(row.get('media_types') or [])}",
            "",
            f"模型导入建议: {row.get('model_hint', '') or '无'}",
            f"知识库导入建议: {row.get('knowledge_hint', '') or '无'}",
        ]
        self.expert_detail_text.configure(state="normal")
        self.expert_detail_text.delete("1.0", tk.END)
        self.expert_detail_text.insert("1.0", "\n".join(lines))
        self.expert_detail_text.configure(state="disabled")

    def _populate_expert_tree(self) -> None:
        if self.expert_tree is None:
            return
        try:
            if not self.expert_tree.winfo_exists():
                return
        except Exception:
            return
        self.expert_tree.delete(*self.expert_tree.get_children())
        for row in self.expert_catalog:
            self.expert_tree.insert(
                "",
                "end",
                iid=row["expert_code"],
                values=(
                    row["display_name"],
                    row["category"],
                    "已导入" if row.get("asset_ready") else "待导入",
                    "已就绪" if row.get("knowledge_ready") else "待导入",
                ),
            )
        if self.expert_catalog:
            first_code = self.expert_catalog[0]["expert_code"]
            self.expert_tree.selection_set(first_code)
            self._render_expert_detail(self.expert_catalog[0])
        self.expert_status_var.set(f"已加载 {len(self.expert_catalog)} 个专家模型条目")

    def _on_expert_tree_select(self, _event: tk.Event | None = None) -> None:
        row = self._selected_expert_row()
        if row is not None:
            self._render_expert_detail(row)

    def _import_selected_expert_assets(self, choose_folder: bool = False) -> None:
        row = self._selected_expert_row()
        if row is None:
            self.expert_status_var.set("请先选择一个专家")
            self.hero_var.set("请先选择一个专家")
            return
        if choose_folder:
            directory = filedialog.askdirectory(parent=self.expert_window or self.root, title="选择专家模型")
            if not directory:
                return
            paths = [directory]
        else:
            paths = list(
                filedialog.askopenfilenames(
                    parent=self.expert_window or self.root,
                    title="选择专家模型文件或权重文件",
                    filetypes=[("All Files", "*.*")],
                )
            )
            if not paths:
                return
        self.expert_status_var.set(f"正在导入 {row['display_name']} 的专家模型")
        self._dispatch("expert_import", lambda: self.runtime.import_expert_assets(row["expert_code"], paths))

    def _import_selected_expert_knowledge_text(self) -> None:
        row = self._selected_expert_row()
        if row is None:
            self.expert_status_var.set("请先选择一个专家")
            self.hero_var.set("请先选择一个专家")
            return
        self._import_knowledge_files(row["knowledge_scope"])

    def _import_selected_expert_knowledge_media(self) -> None:
        row = self._selected_expert_row()
        if row is None:
            self.expert_status_var.set("请先选择一个专家")
            self.hero_var.set("请先选择一个专家")
            return
        self._import_knowledge_media_files(row["knowledge_scope"])

    def _show_expert_window(self) -> None:
        self._log_gui_action("open_expert_window")
        self._select_dashboard_tab("expert")
        self._refresh_expert_catalog()
        return

        window = tk.Toplevel(self.root)
        window.title(f"{APP_DISPLAY_NAME} - 专家模型管理")
        self._set_window_geometry(window, min(1220, int(self.window_width * 0.76)), min(840, int(self.window_height * 0.82)), 920, 640)
        window.configure(bg="#0f1720")
        window.transient(self.root)
        self._apply_window_icon(window)
        self.window_refs.append(window)
        self.expert_window = window

        def _close_window() -> None:
            self.expert_window = None
            window.destroy()

        window.protocol("WM_DELETE_WINDOW", _close_window)

        shell = ttk.Frame(window, style="Root.TFrame", padding=18)
        shell.pack(fill="both", expand=True)
        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(1, weight=1)

        header = ttk.Frame(shell, style="Panel.TFrame", padding=16)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="专家模型管理", style="Header.TLabel").grid(row=0, column=0, sticky="w")
        expert_header_hint = ttk.Label(
            header,
            text="默认发布版不内置大体积专家模型。请按需导入模型资产；需要知识库的专家，再导入对应知识文件。",
            style="Body.TLabel",
            justify="left",
        )
        expert_header_hint.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        self._register_adaptive_wrap_label(expert_header_hint, header, padding=36, min_width=320, max_width=920)

        body = ttk.Frame(shell, style="Panel.TFrame", padding=16)
        body.grid(row=1, column=0, sticky="nsew", pady=(16, 0))
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(1, weight=1)

        topbar = ttk.Frame(body, style="SoftPanel.TFrame", padding=12)
        topbar.grid(row=0, column=0, columnspan=2, sticky="ew")
        self._grid_action_bar(
            topbar,
            [
                ttk.Button(topbar, text="导入模型文件", command=lambda: self._import_selected_expert_assets(False)),
                ttk.Button(topbar, text="导入模型", command=lambda: self._import_selected_expert_assets(True)),
                ttk.Button(topbar, text="导入该专家知识文本", command=self._import_selected_expert_knowledge_text),
                ttk.Button(topbar, text="导入该专家媒体知识", command=self._import_selected_expert_knowledge_media),
                ttk.Button(topbar, text="刷新专家", command=self._refresh_expert_catalog),
            ],
            columns=3,
        )

        table_wrap = ttk.Frame(body, style="SoftPanel.TFrame", padding=12)
        table_wrap.grid(row=1, column=0, sticky="nsew", pady=(14, 0), padx=(0, 10))
        table_wrap.columnconfigure(0, weight=1)
        table_wrap.rowconfigure(0, weight=1)

        self.expert_tree = ttk.Treeview(table_wrap, columns=("name", "category", "asset", "kb"), show="headings")
        self.expert_tree.heading("name", text="专家名称")
        self.expert_tree.heading("category", text="类别")
        self.expert_tree.heading("asset", text="模型状态")
        self.expert_tree.heading("kb", text="知识库状态")
        self.expert_tree.column("name", width=260, anchor="w")
        self.expert_tree.column("category", width=120, anchor="center")
        self.expert_tree.column("asset", width=100, anchor="center")
        self.expert_tree.column("kb", width=110, anchor="center")
        self.expert_tree.grid(row=0, column=0, sticky="nsew")
        self.expert_tree.bind("<<TreeviewSelect>>", self._on_expert_tree_select)
        expert_scroll = ttk.Scrollbar(table_wrap, orient="vertical", command=self.expert_tree.yview)
        expert_scroll.grid(row=0, column=1, sticky="ns")
        self.expert_tree.configure(yscrollcommand=expert_scroll.set)

        detail_wrap = ttk.Frame(body, style="SoftPanel.TFrame", padding=12)
        detail_wrap.grid(row=1, column=1, sticky="nsew", pady=(14, 0))
        detail_wrap.columnconfigure(0, weight=1)
        detail_wrap.rowconfigure(1, weight=1)
        ttk.Label(detail_wrap, text="专家详情", style="PanelTitle.TLabel").grid(row=0, column=0, sticky="w")
        self.expert_detail_text = tk.Text(detail_wrap, bg="#0f1720", fg="#dbe6f2", insertbackground="#dbe6f2", relief="flat", font=("Microsoft YaHei UI", 10), wrap="word")
        self.expert_detail_text.grid(row=1, column=0, sticky="nsew", pady=(12, 0))
        self.expert_detail_text.configure(state="disabled")
        self._register_scroll_target(self.expert_tree, self.expert_tree)
        self._register_scroll_target(detail_wrap, self.expert_detail_text)
        self._register_scroll_target(self.expert_detail_text, self.expert_detail_text)

        footer = ttk.Frame(shell, style="Panel.TFrame", padding=(10, 12))
        footer.grid(row=2, column=0, sticky="ew", pady=(16, 0))
        footer.columnconfigure(0, weight=1)
        expert_status_label = ttk.Label(footer, textvariable=self.expert_status_var, style="Foot.TLabel", justify="left")
        expert_status_label.grid(row=0, column=0, sticky="ew")
        self._register_adaptive_wrap_label(expert_status_label, footer, padding=24, min_width=320, max_width=1080)
        ttk.Button(footer, text="关闭", command=_close_window).grid(row=0, column=1, sticky="e")

        self._populate_expert_tree()
        self._refresh_expert_catalog()

    def _refresh_archive_catalog(self) -> None:
        self.hero_var.set("正在刷新训练工作台")
        self._dispatch("archive_catalog", self.runtime.get_archive_catalog)

    def _render_archive_detail(self, row: Dict[str, Any]) -> None:
        if self.archive_detail_text is None:
            return
        try:
            if not self.archive_detail_text.winfo_exists():
                return
        except Exception:
            return
        try:
            detail = self.runtime.get_archive_detail(str(row.get("session_id", "")))
        except Exception as exc:
            body = f"读取实验档案失败: {exc}"
        else:
            session = detail.get("session", {})
            events = detail.get("events", [])
            lines = [
                f"记录编号: {session.get('session_id', '')}",
                f"实验项目: {session.get('project_name', '')}",
                f"实验名称: {session.get('experiment_name', '')}",
                f"实验人员: {session.get('operator_name', '')}",
                f"标签: {', '.join(session.get('tags') or [])}",
                f"模式: {session.get('mode', '')}",
                f"开始时间: {session.get('opened_at', '')}",
                f"结束时间: {session.get('closed_at', '')}",
                f"事件数量: {len(events)}",
                "",
                "最近事件",
            ]
            if events:
                for item in events[-20:]:
                    payload = item.get("payload") or {}
                    lines.append(f"- [{item.get('timestamp', '')}] {item.get('title', item.get('event_type', ''))}: {json.dumps(payload, ensure_ascii=False)[:240]}")
            else:
                lines.append("- 当前会话暂无事件记录")
            body = "\n".join(lines)
        self.archive_detail_text.configure(state="normal")
        self.archive_detail_text.delete("1.0", tk.END)
        self.archive_detail_text.insert("1.0", body)
        self.archive_detail_text.configure(state="disabled")

    def _populate_archive_tree(self) -> None:
        if self.archive_tree is None:
            return
        try:
            if not self.archive_tree.winfo_exists():
                return
        except Exception:
            return
        self.archive_tree.delete(*self.archive_tree.get_children())
        for row in self.archive_catalog:
            session_id = str(row.get("session_id", ""))
            self.archive_tree.insert(
                "",
                "end",
                iid=session_id,
                values=(
                    _format_archive_record_label(row),
                    row.get("project_name", ""),
                    row.get("experiment_name", ""),
                    row.get("operator_name", ""),
                    row.get("event_count", 0),
                    row.get("opened_at", ""),
                ),
            )
        if self.archive_catalog:
            first = str(self.archive_catalog[0].get("session_id", ""))
            self.archive_tree.selection_set(first)
            self._render_archive_detail(self.archive_catalog[0])
        self.archive_status_var.set(f"已加载 {len(self.archive_catalog)} 份实验档案")

    def _on_archive_tree_select(self, _event: tk.Event | None = None) -> None:
        if self.archive_tree is None:
            return
        selection = self.archive_tree.selection()
        if not selection:
            return
        session_id = selection[0]
        for row in self.archive_catalog:
            if str(row.get("session_id", "")) == session_id:
                self._render_archive_detail(row)
                break

    def _show_archive_window(self) -> None:
        self._log_gui_action("open_archive_window")
        self._select_dashboard_tab("archive")
        self._refresh_archive_catalog()
        return

        window = tk.Toplevel(self.root)
        window.title(f"{APP_DISPLAY_NAME} - 实验档案中心")
        self._set_window_geometry(window, min(1240, int(self.window_width * 0.78)), min(860, int(self.window_height * 0.84)), 960, 680)
        window.configure(bg="#0f1720")
        window.transient(self.root)
        self._apply_window_icon(window)
        self.window_refs.append(window)
        self.archive_window = window

        def _close_window() -> None:
            self.archive_window = None
            window.destroy()

        window.protocol("WM_DELETE_WINDOW", _close_window)
        shell = ttk.Frame(window, style="Root.TFrame", padding=18)
        shell.pack(fill="both", expand=True)
        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(1, weight=1)

        header = ttk.Frame(shell, style="Panel.TFrame", padding=16)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="实验档案中心", style="Header.TLabel").grid(row=0, column=0, sticky="w")
        archive_header_hint = ttk.Label(header, text="按实验项目、实验名称、实验人员和时间检索运行归档。", style="Body.TLabel", justify="left")
        archive_header_hint.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        self._register_adaptive_wrap_label(archive_header_hint, header, padding=36, min_width=320, max_width=920)

        body = ttk.Frame(shell, style="Panel.TFrame", padding=16)
        body.grid(row=1, column=0, sticky="nsew", pady=(16, 0))
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(0, weight=1)

        table_wrap = ttk.Frame(body, style="SoftPanel.TFrame", padding=12)
        table_wrap.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        table_wrap.columnconfigure(0, weight=1)
        table_wrap.rowconfigure(0, weight=1)
        self.archive_tree = ttk.Treeview(table_wrap, columns=("id", "project", "experiment", "operator", "events", "opened"), show="headings")
        for key, label, width in [("id", "记录", 180), ("project", "项目", 180), ("experiment", "实验", 180), ("operator", "人员", 100), ("events", "事件数", 70), ("opened", "开始时间", 150)]:
            self.archive_tree.heading(key, text=label)
            self.archive_tree.column(key, width=width, anchor="w" if key not in {"events"} else "center")
        self.archive_tree.grid(row=0, column=0, sticky="nsew")
        self.archive_tree.bind("<<TreeviewSelect>>", self._on_archive_tree_select)
        tree_scroll = ttk.Scrollbar(table_wrap, orient="vertical", command=self.archive_tree.yview)
        tree_scroll.grid(row=0, column=1, sticky="ns")
        self.archive_tree.configure(yscrollcommand=tree_scroll.set)

        detail_wrap = ttk.Frame(body, style="SoftPanel.TFrame", padding=12)
        detail_wrap.grid(row=0, column=1, sticky="nsew")
        detail_wrap.columnconfigure(0, weight=1)
        detail_wrap.rowconfigure(1, weight=1)
        ttk.Label(detail_wrap, text="档案详情", style="PanelTitle.TLabel").grid(row=0, column=0, sticky="w")
        self.archive_detail_text = tk.Text(detail_wrap, bg="#0f1720", fg="#dbe6f2", insertbackground="#dbe6f2", relief="flat", font=("Microsoft YaHei UI", 10), wrap="word")
        self.archive_detail_text.grid(row=1, column=0, sticky="nsew", pady=(12, 0))
        self.archive_detail_text.configure(state="disabled")

        footer = ttk.Frame(shell, style="Panel.TFrame", padding=(10, 12))
        footer.grid(row=2, column=0, sticky="ew", pady=(16, 0))
        footer.columnconfigure(0, weight=1)
        archive_status_label = ttk.Label(footer, textvariable=self.archive_status_var, style="Foot.TLabel", justify="left")
        archive_status_label.grid(row=0, column=0, sticky="ew")
        self._register_adaptive_wrap_label(archive_status_label, footer, padding=24, min_width=320, max_width=1080)
        ttk.Button(footer, text="刷新列表", command=self._refresh_archive_catalog).grid(row=0, column=1, sticky="e", padx=(0, 8))
        ttk.Button(footer, text="关闭", command=_close_window).grid(row=0, column=2, sticky="e")

        self._register_scroll_target(self.archive_tree, self.archive_tree)
        self._register_scroll_target(detail_wrap, self.archive_detail_text)
        self._register_scroll_target(self.archive_detail_text, self.archive_detail_text)
        self._refresh_archive_catalog()

    def _pick_paths_for_import(self, title: str, filetypes: list[tuple[str, str]]) -> List[str]:
        files = list(filedialog.askopenfilenames(parent=self.training_window or self.root, title=title, filetypes=filetypes))
        if files:
            return files
        directory = filedialog.askdirectory(parent=self.training_window or self.root, title=f"{title}（也可选择目录）")
        return [directory] if directory else []

    def _refresh_training_overview(self) -> None:
        if self.runtime is None:
            self.training_status_var.set("训练工作台尚未完成初始化，请稍候再试。")
            self._render_training_overview()
            return
        self.hero_var.set("正在准备 NeuroLab Hub 可视化界面")
        self._dispatch("training_overview", self.runtime.get_training_overview)

    def _render_training_overview(self) -> None:
        if self.training_detail_text is None:
            return
        try:
            if not self.training_detail_text.winfo_exists():
                return
        except Exception:
            return
        overview = self.training_overview or {}
        assets = overview.get("assets") or {}
        lines = [
            f"最近工作区: {overview.get('latest_workspace', '') or '-'}",
            f"训练任务数: {overview.get('job_count', 0)}",
            f"LLM 真实样本: {assets.get('llm_total_samples', 0)}",
            f"Pi 数据集数: {assets.get('pi_dataset_count', 0)}",
            f"Pi 样本数: {assets.get('pi_total_samples', 0)}",
            "",
            "最近任务",
        ]
        jobs = overview.get("jobs") or []
        if jobs:
            for job in jobs[-20:]:
                lines.append(f"- {job.get('job_id', '')} | {job.get('kind', '')} | {job.get('status', '')} | {job.get('created_at', '')}")
                if job.get("result"):
                    lines.append(f"  结果: {json.dumps(job.get('result'), ensure_ascii=False)[:300]}")
                if job.get("error"):
                    lines.append(f"  错误: {str(job.get('error'))[:300]}")
        else:
            lines.append("- 当前没有训练任务")
        self.training_detail_text.configure(state="normal")
        self.training_detail_text.delete("1.0", tk.END)
        self.training_detail_text.insert("1.0", "\n".join(lines))
        self.training_detail_text.configure(state="disabled")

    def _build_training_workspace_from_form(self) -> None:
        workspace_name = self.training_workspace_entry.get().strip() if self.training_workspace_entry is not None else ""
        self.training_status_var.set("正在构建训练工作区")
        self._dispatch("training_workspace", lambda: self.runtime.build_training_workspace(workspace_name))

    def _import_llm_dataset_from_dialog(self) -> None:
        paths = self._pick_paths_for_import(
            "导入 LLM 微调数据",
            [("训练数据", "*.jsonl;*.json;*.csv;*.txt;*.md"), ("所有文件", "*.*")],
        )
        if not paths:
            return
        self.training_status_var.set("正在导入 LLM 微调数据")
        self._dispatch("training_import_llm", lambda: self.runtime.import_llm_training_data(paths))

    def _import_pi_dataset_from_dialog(self) -> None:
        paths = self._pick_paths_for_import(
            "导入 Pi 检测训练数据",
            [("Pi 数据集", "*.zip;*.jpg;*.jpeg;*.png;*.bmp;*.webp"), ("所有文件", "*.*")],
        )
        if not paths:
            return
        self.training_status_var.set("正在导入 Pi 检测训练数据")
        self._dispatch("training_import_pi", lambda: self.runtime.import_pi_training_data(paths))

    def _start_llm_training_from_form(self) -> None:
        workspace_dir = str((self.training_overview or {}).get("latest_workspace") or "").strip()
        if not workspace_dir:
            self.training_status_var.set("请先构建训练工作区")
            self.hero_var.set("请先构建训练工作区")
            return
        base_model = self.training_base_model_entry.get().strip() if self.training_base_model_entry is not None else ""
        self.training_status_var.set("正在启动 LLM 微调")
        self._dispatch("training_llm", lambda: self.runtime.start_llm_finetune({"workspace_dir": workspace_dir, "base_model": base_model}))

    def _start_pi_training_from_form(self) -> None:
        workspace_dir = str((self.training_overview or {}).get("latest_workspace") or "").strip()
        if not workspace_dir:
            self.training_status_var.set("请先构建训练工作区")
            self.hero_var.set("请先构建训练工作区")
            return
        base_weights = self.training_pi_weights_entry.get().strip() if self.training_pi_weights_entry is not None else ""
        self.training_status_var.set("正在启动 Pi 检测模型微调")
        self._dispatch("training_pi", lambda: self.runtime.start_pi_detector_finetune({"workspace_dir": workspace_dir, "base_weights": base_weights}))

    def _request_training_annotation_workspace_prepare(self) -> None:
        if self.runtime is None:
            self.training_annotation_status_var.set("训练工作台尚未完成初始化，请稍候再试。")
            return
        if self.training_annotation_workspace_pending:
            return
        workspace_name = self.training_workspace_entry.get().strip() if self.training_workspace_entry is not None else ""
        self.training_annotation_workspace_pending = True
        self.training_annotation_status_var.set("正在准备标注工作区，请稍候。")
        self._dispatch("training_workspace", lambda: self.runtime.build_training_workspace(workspace_name))

    def _ensure_training_annotation_workspace(self, *, auto_prepare: bool = False) -> str:
        workspace_dir = str((self.training_overview or {}).get("latest_workspace") or "").strip()
        if not workspace_dir:
            if auto_prepare:
                self._request_training_annotation_workspace_prepare()
            return ""
        self.training_annotation_workspace_dir = workspace_dir
        return workspace_dir

    def _refresh_training_annotation_panel(self) -> None:
        if self.training_annotation_tree is None:
            return
        workspace_dir = self._ensure_training_annotation_workspace(auto_prepare=True)
        if not workspace_dir:
            self.training_annotation_items = []
            self.training_annotation_tree.delete(*self.training_annotation_tree.get_children())
            self.training_annotation_current_item = {}
            self.training_annotation_boxes = []
            self._sync_annotation_box_tree()
            if self.training_annotation_canvas is not None:
                self.training_annotation_canvas.delete("all")
            if not self.training_annotation_workspace_pending:
                self.training_annotation_status_var.set("请先构建训练工作区，然后导入训练图片。")
            return
        self.training_annotation_items = annotation_store.list_images(workspace_dir)
        self.training_annotation_tree.delete(*self.training_annotation_tree.get_children())
        for row in self.training_annotation_items:
            self.training_annotation_tree.insert("", tk.END, iid=row["name"], values=(row["name"], len(row.get("boxes") or [])))
        class_count = len(annotation_store.get_classes(workspace_dir))
        self.training_annotation_status_var.set(f"当前图片 {len(self.training_annotation_items)} 张 | 类别 {class_count} 个")

    def _sync_annotation_box_tree(self) -> None:
        if self.training_annotation_box_tree is None:
            return
        self.training_annotation_box_tree.delete(*self.training_annotation_box_tree.get_children())
        for index, box in enumerate(self.training_annotation_boxes):
            self.training_annotation_box_tree.insert(
                "",
                tk.END,
                iid=str(index),
                values=(
                    index + 1,
                    box.get("class_name", ""),
                    int(abs(float(box.get("x2", 0.0)) - float(box.get("x1", 0.0)))),
                    int(abs(float(box.get("y2", 0.0)) - float(box.get("y1", 0.0)))),
                ),
            )

    def _on_training_annotation_select(self, _event: Any = None) -> None:
        if self.training_annotation_tree is None:
            return
        selection = self.training_annotation_tree.selection()
        if not selection:
            return
        image_name = selection[0]
        for row in self.training_annotation_items:
            if row.get("name") == image_name:
                self.training_annotation_current_item = row
                self.training_annotation_boxes = [dict(item) for item in row.get("boxes") or []]
                self._sync_annotation_box_tree()
                self._render_training_annotation_image()
                self.training_annotation_status_var.set(f"已加载图片: {image_name}")
                break

    def _render_training_annotation_image(self) -> None:
        if self.training_annotation_canvas is None:
            return
        image_path = str(self.training_annotation_current_item.get("image_path") or "").strip()
        if not image_path:
            self.training_annotation_canvas.delete("all")
            return
        image = Image.open(image_path).convert("RGB")
        original_width, original_height = image.size
        self.training_annotation_image_size = (original_width, original_height)
        canvas_width = max(int(self.training_annotation_canvas.winfo_width() or 760), 320)
        canvas_height = max(int(self.training_annotation_canvas.winfo_height() or 420), 240)
        scale = min(canvas_width / max(original_width, 1), canvas_height / max(original_height, 1))
        scale = max(min(scale, 1.8), 0.1)
        preview_width = max(1, int(original_width * scale))
        preview_height = max(1, int(original_height * scale))
        offset_x = max((canvas_width - preview_width) // 2, 0)
        offset_y = max((canvas_height - preview_height) // 2, 0)
        preview = image.resize((preview_width, preview_height), Image.Resampling.LANCZOS)
        self.training_annotation_photo = ImageTk.PhotoImage(preview)
        self.training_annotation_scale = scale
        self.training_annotation_offset = (offset_x, offset_y)
        self.training_annotation_canvas.delete("all")
        self.training_annotation_canvas.create_image(offset_x, offset_y, anchor="nw", image=self.training_annotation_photo)
        self._redraw_training_annotation_overlay()

    def _redraw_training_annotation_overlay(self) -> None:
        if self.training_annotation_canvas is None:
            return
        self.training_annotation_canvas.delete("annotation_box")
        offset_x, offset_y = self.training_annotation_offset
        scale = self.training_annotation_scale
        for box in self.training_annotation_boxes:
            x1 = offset_x + float(box.get("x1", 0.0)) * scale
            y1 = offset_y + float(box.get("y1", 0.0)) * scale
            x2 = offset_x + float(box.get("x2", 0.0)) * scale
            y2 = offset_y + float(box.get("y2", 0.0)) * scale
            self.training_annotation_canvas.create_rectangle(x1, y1, x2, y2, outline="#20c997", width=2, tags=("annotation_box",))
            self.training_annotation_canvas.create_text(
                x1 + 6,
                y1 + 6,
                anchor="nw",
                text=str(box.get("class_name", "")),
                fill="#20c997",
                font=("Microsoft YaHei UI", 10, "bold"),
                tags=("annotation_box",),
            )

    def _annotation_canvas_to_image(self, event_x: int, event_y: int) -> tuple[float, float]:
        offset_x, offset_y = self.training_annotation_offset
        scale = max(self.training_annotation_scale, 1e-6)
        width, height = self.training_annotation_image_size
        return (
            max(0.0, min((event_x - offset_x) / scale, float(width))),
            max(0.0, min((event_y - offset_y) / scale, float(height))),
        )

    def _on_training_annotation_press(self, event: tk.Event) -> None:
        if not self.training_annotation_current_item:
            return
        self.training_annotation_drag_start = (event.x, event.y)
        if self.training_annotation_canvas is not None and self.training_annotation_preview_rect is not None:
            self.training_annotation_canvas.delete(self.training_annotation_preview_rect)
            self.training_annotation_preview_rect = None

    def _on_training_annotation_drag(self, event: tk.Event) -> None:
        if self.training_annotation_canvas is None or self.training_annotation_drag_start is None:
            return
        x0, y0 = self.training_annotation_drag_start
        if self.training_annotation_preview_rect is None:
            self.training_annotation_preview_rect = self.training_annotation_canvas.create_rectangle(
                x0,
                y0,
                event.x,
                event.y,
                outline="#ffd166",
                width=2,
                dash=(4, 2),
            )
        else:
            self.training_annotation_canvas.coords(self.training_annotation_preview_rect, x0, y0, event.x, event.y)

    def _on_training_annotation_release(self, event: tk.Event) -> None:
        if self.training_annotation_drag_start is None:
            return
        if self.training_annotation_canvas is not None and self.training_annotation_preview_rect is not None:
            self.training_annotation_canvas.delete(self.training_annotation_preview_rect)
            self.training_annotation_preview_rect = None
        start_x, start_y = self.training_annotation_drag_start
        self.training_annotation_drag_start = None
        class_name = self.training_annotation_class_entry.get().strip() if self.training_annotation_class_entry is not None else ""
        if not class_name:
            self.training_annotation_status_var.set("请先输入当前标注类别")
            return
        x1, y1 = self._annotation_canvas_to_image(start_x, start_y)
        x2, y2 = self._annotation_canvas_to_image(event.x, event.y)
        if abs(x2 - x1) < 4 or abs(y2 - y1) < 4:
            return
        self.training_annotation_boxes.append(
            {"class_name": class_name, "x1": min(x1, x2), "y1": min(y1, y2), "x2": max(x1, x2), "y2": max(y1, y2)}
        )
        self._sync_annotation_box_tree()
        self._redraw_training_annotation_overlay()
        self.training_annotation_status_var.set(f"已新增标注框 {len(self.training_annotation_boxes)} 个")

    def _save_training_annotations(self) -> None:
        if not self.training_annotation_current_item:
            self.training_annotation_status_var.set("请先选择一张训练图片")
            return
        workspace_dir = self._ensure_training_annotation_workspace()
        if not workspace_dir:
            self.training_annotation_status_var.set("请先构建训练工作区")
            return
        width, height = self.training_annotation_image_size
        summary = annotation_store.save_annotations(
            workspace_dir,
            str(self.training_annotation_current_item.get("name") or ""),
            width,
            height,
            self.training_annotation_boxes,
        )
        self.training_annotation_status_var.set(f"标注已保存: {summary['image_name']} | 框 {summary['box_count']} 个 | 类别 {len(summary['class_names'])} 个")
        self._refresh_training_overview()
        self._refresh_training_annotation_panel()

    def _clear_training_annotation_boxes(self) -> None:
        self.training_annotation_boxes = []
        self._sync_annotation_box_tree()
        self._redraw_training_annotation_overlay()
        self.training_annotation_status_var.set("已清空当前图片标注框")

    def _delete_selected_training_box(self) -> None:
        if self.training_annotation_box_tree is None:
            return
        selection = self.training_annotation_box_tree.selection()
        if not selection:
            return
        for row_id in sorted((int(item) for item in selection), reverse=True):
            if 0 <= row_id < len(self.training_annotation_boxes):
                self.training_annotation_boxes.pop(row_id)
        self._sync_annotation_box_tree()
        self._redraw_training_annotation_overlay()
        self.training_annotation_status_var.set("已删除选中标注框")

    def _import_training_annotation_images(self) -> None:
        paths = self._pick_paths_for_import(
            "导入待标注图片",
            [("图片文件", "*.jpg;*.jpeg;*.png;*.bmp;*.webp"), ("所有文件", "*.*")],
        )
        if not paths:
            return
        workspace_dir = self._ensure_training_annotation_workspace()
        if not workspace_dir:
            self.training_annotation_status_var.set("请先构建训练工作区")
            return
        summary = annotation_store.import_images(workspace_dir, paths)
        self.training_annotation_status_var.set(f"已导入图片 {summary['imported_count']} 张")
        self._refresh_training_overview()
        self._refresh_training_annotation_panel()

    def _generate_training_annotation_samples(self) -> None:
        workspace_dir = self._ensure_training_annotation_workspace()
        if not workspace_dir:
            self.training_annotation_status_var.set("请先构建训练工作区")
            return
        sample_root = Path(workspace_dir) / "synthetic_samples"
        sample_root.mkdir(parents=True, exist_ok=True)
        generated_paths: List[str] = []
        samples = [
            ("sample_flask.png", "FLASK", (90, 70, 390, 350), (40, 170, 240)),
            ("sample_warning.png", "DANGER", (110, 120, 430, 300), (220, 60, 60)),
            ("sample_screen.png", "OCR", (70, 110, 470, 290), (60, 80, 200)),
        ]
        for name, label, rect, color in samples:
            canvas = 255 * np.ones((420, 560, 3), dtype=np.uint8)
            x1, y1, x2, y2 = rect
            cv2.rectangle(canvas, (x1, y1), (x2, y2), color, thickness=-1)
            cv2.rectangle(canvas, (x1, y1), (x2, y2), (20, 20, 20), thickness=3)
            cv2.putText(canvas, label, (x1 + 24, y1 + 84), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (255, 255, 255), 3, cv2.LINE_AA)
            output = sample_root / name
            cv2.imwrite(str(output), canvas)
            generated_paths.append(str(output))
        annotation_store.import_images(workspace_dir, generated_paths)
        self.training_annotation_status_var.set(f"已生成并导入测试图片 {len(generated_paths)} 张")
        self._refresh_training_overview()
        self._refresh_training_annotation_panel()

    def _start_full_training_from_form(self) -> None:
        workspace_dir = str((self.training_overview or {}).get("latest_workspace") or "").strip()
        if not workspace_dir:
            self.training_status_var.set("请先构建训练工作区")
            self.hero_var.set("请先构建训练工作区")
            return
        base_model = self.training_base_model_entry.get().strip() if self.training_base_model_entry is not None else ""
        base_weights = self.training_pi_weights_entry.get().strip() if self.training_pi_weights_entry is not None else ""
        self.training_status_var.set("正在启动一键全流程训练")
        self._dispatch(
            "training_all",
            lambda: self.runtime.start_full_training_pipeline(
                {"workspace_dir": workspace_dir, "base_model": base_model, "base_weights": base_weights}
            ),
        )

    def _focus_training_section(self, focus: str = "") -> None:
        focus_key = (focus or "").strip().lower()
        if self.training_notebook is not None:
            if focus_key == "llm":
                self.training_notebook.select(0)
            elif focus_key in {"vision", "yolo"}:
                self.training_notebook.select(1)
        if focus_key == "llm" and self.training_base_model_entry is not None:
            self.training_base_model_entry.focus_set()
            self.training_status_var.set("当前工作台：LLM 工作台")
            self.hero_var.set("已进入 LLM 工作台")
        elif focus_key in {"vision", "yolo"} and self.training_pi_weights_entry is not None:
            self.training_pi_weights_entry.focus_set()
            self.training_status_var.set("当前工作台：YOLO 工作台")
            self.hero_var.set("已进入 YOLO 工作台")
        else:
            self.training_status_var.set("训练工作台已就绪")

    def _show_training_window(self, focus: str = "") -> None:
        self._log_gui_action("open_training_window", focus=focus or "")
        if self.runtime is None:
            self.training_status_var.set("训练工作台尚未完成初始化，正在等待主控制台加载")
            self.root.after(300, lambda: self._show_training_window(focus))
            return
        self._select_dashboard_tab("training")
        self._refresh_training_overview()
        self._focus_training_section(focus)
        return

        window = tk.Toplevel(self.root)
        window.title(f"{APP_DISPLAY_NAME} - 训练工作台")
        self._set_window_geometry(window, 1120, 820, 900, 680)
        window.configure(bg="#0f1720")
        window.transient(self.root)
        self._apply_window_icon(window)
        self.window_refs.append(window)
        self.training_window = window

        def _close_window() -> None:
            self.training_window = None
            self.training_notebook = None
            self.training_annotation_canvas = None
            self.training_annotation_tree = None
            self.training_annotation_box_tree = None
            self.training_annotation_class_entry = None
            self.training_annotation_photo = None
            self.training_annotation_current_item = {}
            self.training_annotation_boxes = []
            window.destroy()

        window.protocol("WM_DELETE_WINDOW", _close_window)
        shell = ttk.Frame(window, style="Root.TFrame", padding=18)
        shell.pack(fill="both", expand=True)
        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(1, weight=1)

        header = ttk.Frame(shell, style="Panel.TFrame", padding=16)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="训练工作台", style="Header.TLabel").grid(row=0, column=0, sticky="w")
        training_header_hint = ttk.Label(header, text="LLM 与 YOLO 训练能力已拆分为两个独立工作台，可分别导入数据并启动训练。", style="Body.TLabel", justify="left")
        training_header_hint.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        self._register_adaptive_wrap_label(training_header_hint, header, padding=36, min_width=320, max_width=920)

        body = ttk.Frame(shell, style="Panel.TFrame", padding=16)
        body.grid(row=1, column=0, sticky="nsew", pady=(16, 0))
        body.columnconfigure(0, weight=1)
        body.rowconfigure(3, weight=1)

        form = ttk.Frame(body, style="SoftPanel.TFrame", padding=12)
        form.grid(row=0, column=0, sticky="ew")
        form.columnconfigure(1, weight=1)
        ttk.Label(form, text="工作区名称", style="Body.TLabel").grid(row=0, column=0, sticky="w")
        self.training_workspace_entry = ttk.Entry(form)
        self.training_workspace_entry.grid(row=0, column=1, sticky="ew", padx=(10, 0))
        self.training_workspace_entry.insert(0, str(get_config("training.workspace_name", "neurolab_hub_training")))

        common_actions = ttk.Frame(body, style="SoftPanel.TFrame", padding=12)
        common_actions.grid(row=1, column=0, sticky="ew", pady=(14, 0))
        self._grid_action_bar(
            common_actions,
            [
                ttk.Button(common_actions, text="构建工作区", command=self._build_training_workspace_from_form),
                ttk.Button(common_actions, text="一键全流程", command=self._start_full_training_from_form),
                ttk.Button(common_actions, text="刷新概览", command=self._refresh_training_overview),
                ttk.Button(common_actions, text="关闭", command=_close_window),
            ],
            columns=4,
        )

        self.training_notebook = ttk.Notebook(body)
        self.training_notebook.grid(row=2, column=0, sticky="nsew", pady=(14, 0))

        llm_tab = ttk.Frame(self.training_notebook, style="Panel.TFrame", padding=14)
        llm_tab.columnconfigure(0, weight=1)
        ttk.Label(llm_tab, text="LLM 训练工作台", style="PanelTitle.TLabel").grid(row=0, column=0, sticky="w")
        llm_hint_label = ttk.Label(llm_tab, text="面向 SFT / 指令微调流程，独立导入数据并启动 LLM 训练。", style="Body.TLabel", justify="left")
        llm_hint_label.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        self._register_adaptive_wrap_label(llm_hint_label, llm_tab, padding=36, min_width=320, max_width=980)
        llm_form = ttk.Frame(llm_tab, style="SoftPanel.TFrame", padding=12)
        llm_form.grid(row=2, column=0, sticky="ew", pady=(14, 0))
        llm_form.columnconfigure(1, weight=1)
        ttk.Label(llm_form, text="LLM 基础模型", style="Body.TLabel").grid(row=0, column=0, sticky="w")
        self.training_base_model_entry = ttk.Entry(llm_form)
        self.training_base_model_entry.grid(row=0, column=1, sticky="ew", padx=(10, 0))
        self.training_base_model_entry.insert(0, str(get_config("training.llm_base_model", "")))
        llm_actions = ttk.Frame(llm_tab, style="SoftPanel.TFrame", padding=12)
        llm_actions.grid(row=3, column=0, sticky="ew", pady=(14, 0))
        self._grid_action_bar(
            llm_actions,
            [
                ttk.Button(llm_actions, text="导入 LLM 数据", command=self._import_llm_dataset_from_dialog),
                ttk.Button(llm_actions, text="启动 LLM 训练", command=self._start_llm_training_from_form),
            ],
            columns=2,
        )

        vision_tab = ttk.Frame(self.training_notebook, style="Panel.TFrame", padding=14)
        vision_tab.columnconfigure(0, weight=1)
        vision_tab.rowconfigure(5, weight=1)
        ttk.Label(vision_tab, text="YOLO 训练工作台", style="PanelTitle.TLabel").grid(row=0, column=0, sticky="w")
        vision_hint_label = ttk.Label(vision_tab, text="把图片导入、框选标注和 YOLO 训练放到一个面板里，方便用户持续补数据和测试。", style="Body.TLabel", justify="left")
        vision_hint_label.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        self._register_adaptive_wrap_label(vision_hint_label, vision_tab, padding=36, min_width=320, max_width=980)
        vision_form = ttk.Frame(vision_tab, style="SoftPanel.TFrame", padding=12)
        vision_form.grid(row=2, column=0, sticky="ew", pady=(14, 0))
        vision_form.columnconfigure(1, weight=1)
        ttk.Label(vision_form, text="YOLO 基础权重", style="Body.TLabel").grid(row=0, column=0, sticky="w")
        self.training_pi_weights_entry = ttk.Entry(vision_form)
        self.training_pi_weights_entry.grid(row=0, column=1, sticky="ew", padx=(10, 0))
        self.training_pi_weights_entry.insert(0, str(get_config("training.pi_base_weights", "yolov8n.pt")))
        vision_actions = ttk.Frame(vision_tab, style="SoftPanel.TFrame", padding=12)
        vision_actions.grid(row=3, column=0, sticky="ew", pady=(14, 0))
        self._grid_action_bar(
            vision_actions,
            [
                ttk.Button(vision_actions, text="导入 YOLO 数据", command=self._import_pi_dataset_from_dialog),
                ttk.Button(vision_actions, text="启动 YOLO 训练", command=self._start_pi_training_from_form),
            ],
            columns=2,
        )
        annotation_actions = ttk.Frame(vision_tab, style="SoftPanel.TFrame", padding=12)
        annotation_actions.grid(row=4, column=0, sticky="ew", pady=(14, 0))
        self._grid_action_bar(
            annotation_actions,
            [
                ttk.Button(annotation_actions, text="导入待标注图片", command=self._import_training_annotation_images),
                ttk.Button(annotation_actions, text="生成测试图片", command=self._generate_training_annotation_samples),
                ttk.Button(annotation_actions, text="刷新标注面板", command=self._refresh_training_annotation_panel),
            ],
            columns=3,
        )

        annotation_panel = ttk.Frame(vision_tab, style="SoftPanel.TFrame", padding=12)
        annotation_panel.grid(row=5, column=0, sticky="nsew", pady=(14, 0))
        annotation_panel.columnconfigure(0, weight=2)
        annotation_panel.columnconfigure(1, weight=5)
        annotation_panel.columnconfigure(2, weight=3)
        annotation_panel.rowconfigure(0, weight=1)

        image_list_wrap = ttk.Frame(annotation_panel, style="Panel.TFrame", padding=10)
        image_list_wrap.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        image_list_wrap.columnconfigure(0, weight=1)
        image_list_wrap.rowconfigure(1, weight=1)
        ttk.Label(image_list_wrap, text="待标注图片", style="PanelTitle.TLabel").grid(row=0, column=0, sticky="w")
        self.training_annotation_tree = ttk.Treeview(image_list_wrap, columns=("image", "boxes"), show="headings", height=12)
        self.training_annotation_tree.heading("image", text="图片")
        self.training_annotation_tree.heading("boxes", text="框数")
        self.training_annotation_tree.column("image", width=180, anchor="w")
        self.training_annotation_tree.column("boxes", width=56, anchor="center")
        self.training_annotation_tree.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
        tree_scroll = ttk.Scrollbar(image_list_wrap, orient="vertical", command=self.training_annotation_tree.yview)
        tree_scroll.grid(row=1, column=1, sticky="ns", pady=(10, 0))
        self.training_annotation_tree.configure(yscrollcommand=tree_scroll.set)
        self.training_annotation_tree.bind("<<TreeviewSelect>>", self._on_training_annotation_select)

        canvas_wrap = ttk.Frame(annotation_panel, style="Panel.TFrame", padding=10)
        canvas_wrap.grid(row=0, column=1, sticky="nsew", padx=(0, 10))
        canvas_wrap.columnconfigure(0, weight=1)
        canvas_wrap.rowconfigure(1, weight=1)
        ttk.Label(canvas_wrap, text="标注画布（拖拽鼠标创建框）", style="PanelTitle.TLabel").grid(row=0, column=0, sticky="w")
        self.training_annotation_canvas = tk.Canvas(canvas_wrap, bg="#081018", highlightthickness=0)
        self.training_annotation_canvas.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
        self.training_annotation_canvas.bind("<Configure>", lambda _event: self._render_training_annotation_image())
        self.training_annotation_canvas.bind("<ButtonPress-1>", self._on_training_annotation_press)
        self.training_annotation_canvas.bind("<B1-Motion>", self._on_training_annotation_drag)
        self.training_annotation_canvas.bind("<ButtonRelease-1>", self._on_training_annotation_release)

        tool_wrap = ttk.Frame(annotation_panel, style="Panel.TFrame", padding=10)
        tool_wrap.grid(row=0, column=2, sticky="nsew")
        tool_wrap.columnconfigure(0, weight=1)
        tool_wrap.rowconfigure(3, weight=1)
        ttk.Label(tool_wrap, text="当前类别", style="PanelTitle.TLabel").grid(row=0, column=0, sticky="w")
        self.training_annotation_class_entry = ttk.Entry(tool_wrap)
        self.training_annotation_class_entry.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        self.training_annotation_class_entry.insert(0, "observation")
        ttk.Label(tool_wrap, text="当前图片标注框", style="PanelTitle.TLabel").grid(row=2, column=0, sticky="w", pady=(14, 0))
        box_wrap = ttk.Frame(tool_wrap, style="Panel.TFrame")
        box_wrap.grid(row=3, column=0, sticky="nsew", pady=(10, 0))
        box_wrap.columnconfigure(0, weight=1)
        box_wrap.rowconfigure(0, weight=1)
        self.training_annotation_box_tree = ttk.Treeview(box_wrap, columns=("id", "class", "w", "h"), show="headings", height=10)
        self.training_annotation_box_tree.heading("id", text="#")
        self.training_annotation_box_tree.heading("class", text="类别")
        self.training_annotation_box_tree.heading("w", text="宽")
        self.training_annotation_box_tree.heading("h", text="高")
        self.training_annotation_box_tree.column("id", width=36, anchor="center")
        self.training_annotation_box_tree.column("class", width=100, anchor="w")
        self.training_annotation_box_tree.column("w", width=50, anchor="center")
        self.training_annotation_box_tree.column("h", width=50, anchor="center")
        self.training_annotation_box_tree.grid(row=0, column=0, sticky="nsew")
        box_scroll = ttk.Scrollbar(box_wrap, orient="vertical", command=self.training_annotation_box_tree.yview)
        box_scroll.grid(row=0, column=1, sticky="ns")
        self.training_annotation_box_tree.configure(yscrollcommand=box_scroll.set)
        box_actions = ttk.Frame(tool_wrap, style="Panel.TFrame")
        box_actions.grid(row=4, column=0, sticky="ew", pady=(12, 0))
        box_actions.columnconfigure(0, weight=1)
        box_actions.columnconfigure(1, weight=1)
        box_actions.columnconfigure(2, weight=1)
        ttk.Button(box_actions, text="保存标注", command=self._save_training_annotations).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ttk.Button(box_actions, text="删除选中框", command=self._delete_selected_training_box).grid(row=0, column=1, sticky="ew", padx=4)
        ttk.Button(box_actions, text="清空当前框", command=self._clear_training_annotation_boxes).grid(row=0, column=2, sticky="ew", padx=(4, 0))
        ttk.Label(tool_wrap, textvariable=self.training_annotation_status_var, style="Body.TLabel", wraplength=280, justify="left").grid(row=5, column=0, sticky="ew", pady=(12, 0))

        self.training_notebook.add(llm_tab, text="LLM 工作台")
        self.training_notebook.add(vision_tab, text="YOLO 工作台")

        detail_wrap = ttk.Frame(body, style="SoftPanel.TFrame", padding=12)
        detail_wrap.grid(row=3, column=0, sticky="nsew", pady=(14, 0))
        detail_wrap.columnconfigure(0, weight=1)
        detail_wrap.rowconfigure(1, weight=1)
        ttk.Label(detail_wrap, text="执行日志", style="PanelTitle.TLabel").grid(row=0, column=0, sticky="w")
        self.training_detail_text = tk.Text(detail_wrap, bg="#0f1720", fg="#dbe6f2", insertbackground="#dbe6f2", relief="flat", font=("Microsoft YaHei UI", 10), wrap="word")
        self.training_detail_text.grid(row=1, column=0, sticky="nsew", pady=(12, 0))
        self.training_detail_text.configure(state="disabled")

        footer = ttk.Frame(shell, style="Panel.TFrame", padding=(10, 12))
        footer.grid(row=2, column=0, sticky="ew", pady=(16, 0))
        footer.columnconfigure(0, weight=1)
        training_status_label = ttk.Label(footer, textvariable=self.training_status_var, style="Foot.TLabel", justify="left")
        training_status_label.grid(row=0, column=0, sticky="ew")
        self._register_adaptive_wrap_label(training_status_label, footer, padding=24, min_width=320, max_width=980)

        self._refresh_training_overview()
        self._refresh_training_annotation_panel()
        self._focus_training_section(focus)
    def _selected_cloud_backend(self) -> str:

        if self.cloud_provider_combo is None:
            return "qwen"
        try:
            if not self.cloud_provider_combo.winfo_exists():
                return "qwen"
        except Exception:
            return "qwen"
        return self.cloud_provider_map.get(self.cloud_provider_combo.get(), "qwen")

    def _sync_cloud_provider_choices(self) -> None:
        self.cloud_provider_map = {}
        self.cloud_provider_reverse = {}
        labels: List[str] = []
        for row in self.cloud_backend_catalog:
            label = row.get("label", row.get("backend", ""))
            labels.append(label)
            self.cloud_provider_map[label] = row["backend"]
            self.cloud_provider_reverse[row["backend"]] = label
        if self.cloud_provider_combo is not None:
            try:
                if not self.cloud_provider_combo.winfo_exists():
                    return
            except Exception:
                return
            self.cloud_provider_combo["values"] = labels
            if labels and not self.cloud_provider_combo.get():
                self.cloud_provider_combo.set(labels[0])

    def _load_selected_cloud_backend_into_form(self) -> None:
        backend = self._selected_cloud_backend()
        for row in self.cloud_backend_catalog:
            if row["backend"] != backend:
                continue
            if self.cloud_api_key_entry is not None:
                try:
                    if not self.cloud_api_key_entry.winfo_exists():
                        return
                except Exception:
                    return
                self.cloud_api_key_entry.delete(0, tk.END)
                self.cloud_api_key_entry.insert(0, str(row.get("api_key", "")))
            if self.cloud_base_url_entry is not None:
                try:
                    if not self.cloud_base_url_entry.winfo_exists():
                        return
                except Exception:
                    return
                self.cloud_base_url_entry.delete(0, tk.END)
                self.cloud_base_url_entry.insert(0, str(row.get("base_url", "")))
            if self.cloud_model_entry is not None:
                try:
                    if not self.cloud_model_entry.winfo_exists():
                        return
                except Exception:
                    return
                self.cloud_model_entry.delete(0, tk.END)
                self.cloud_model_entry.insert(0, str(row.get("model", "")))
            if self.cloud_model_alias_entry is not None:
                try:
                    if not self.cloud_model_alias_entry.winfo_exists():
                        return
                except Exception:
                    return
                self.cloud_model_alias_entry.delete(0, tk.END)
                self.cloud_model_alias_entry.insert(0, str(row.get("display_model_name", row.get("model", ""))))
            configured = "已配置" if row.get("configured") else "待配置"
            self.cloud_status_var.set(f"{row.get('label', backend)} 当前状态：{configured}")
            break

    def _save_cloud_backend_from_form(self) -> None:
        backend = self._selected_cloud_backend()
        api_key = self.cloud_api_key_entry.get().strip() if self.cloud_api_key_entry is not None else ""
        base_url = self.cloud_base_url_entry.get().strip() if self.cloud_base_url_entry is not None else ""
        model = self.cloud_model_entry.get().strip() if self.cloud_model_entry is not None else ""
        model_alias = self.cloud_model_alias_entry.get().strip() if self.cloud_model_alias_entry is not None else ""
        model_display_name = model_alias or model
        if model_display_name:
            items = self._custom_entries_for_backend(backend)
            updated = False
            for item in items:
                if str(item.get("name") or "").strip() == model_display_name:
                    item["model"] = model or model_display_name
                    updated = True
                    break
            if not updated:
                items.append({"name": model_display_name, "model": model or model_display_name})
            self.custom_model_registry[backend] = items
            self._save_custom_model_registry()
            current_backend = self.backend_map.get(self.backend_combo.get(), self.backend_var.get() or "ollama")
            if current_backend == backend:
                self._update_model_choices(selected_model=model_display_name)
        self._log_gui_action("save_cloud_backend_config", backend=backend, model=model, model_alias=model_display_name, has_api_key=bool(api_key), has_base_url=bool(base_url))
        self.cloud_status_var.set("正在保存模型服务配置")
        self._dispatch(
            "cloud_save",
            lambda: self.runtime.save_cloud_backend_config(
                backend,
                api_key=api_key,
                base_url=base_url,
                model=model,
            ),
        )

    def _show_cloud_backend_window(self) -> None:
        self._log_gui_action("open_cloud_backend_window")
        self._select_dashboard_tab("model")
        self._refresh_cloud_backend_catalog()
        current_backend = self.backend_map.get(self.backend_combo.get(), self.backend_var.get() or "ollama")
        label = self.cloud_provider_reverse.get(current_backend)
        if label and self.cloud_provider_combo is not None:
            self.cloud_provider_combo.set(label)
            self._load_selected_cloud_backend_into_form()
        elif self.cloud_provider_combo is not None and self.cloud_provider_combo.get():
            self._load_selected_cloud_backend_into_form()
        return

        window = tk.Toplevel(self.root)
        window.title(f"{APP_DISPLAY_NAME} - 模型服务配置")
        self._set_window_geometry(window, 860, 620, 720, 520)
        window.configure(bg="#0f1720")
        window.transient(self.root)
        self._apply_window_icon(window)
        self.window_refs.append(window)
        self.cloud_window = window

        def _close_window() -> None:
            self.cloud_window = None
            window.destroy()

        window.protocol("WM_DELETE_WINDOW", _close_window)

        shell = ttk.Frame(window, style="Root.TFrame", padding=18)
        shell.pack(fill="both", expand=True)
        shell.columnconfigure(0, weight=1)

        header = ttk.Frame(shell, style="Panel.TFrame", padding=16)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="模型服务配置", style="Header.TLabel").grid(row=0, column=0, sticky="w")
        cloud_header_hint = ttk.Label(
            header,
            text="这里统一配置云端 AI 模型的 API 参数与模型命名。除 Ollama 外，其余模型不会预置候选项，需在这里保存后才会加入左侧“模型选择”。",
            style="Body.TLabel",
            justify="left",
        )
        cloud_header_hint.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        self._register_adaptive_wrap_label(cloud_header_hint, header, padding=36, min_width=320, max_width=720)

        body = ttk.Frame(shell, style="Panel.TFrame", padding=16)
        body.grid(row=1, column=0, sticky="nsew", pady=(16, 0))
        body.columnconfigure(0, weight=1)

        ttk.Label(body, text="当前AI模型", style="Body.TLabel").grid(row=0, column=0, sticky="w")
        self.cloud_provider_combo = ttk.Combobox(body, state="readonly")
        self.cloud_provider_combo.grid(row=1, column=0, sticky="ew", pady=(6, 10))
        self.cloud_provider_combo.bind("<<ComboboxSelected>>", lambda _event: self._load_selected_cloud_backend_into_form())
        self.cloud_api_key_entry = self._add_labeled_entry(body, 2, "API Key")
        self.cloud_base_url_entry = self._add_labeled_entry(body, 3, "Base URL")
        self.cloud_model_entry = self._add_labeled_entry(body, 4, "默认模型")
        self.cloud_model_alias_entry = self._add_labeled_entry(body, 5, "模型命名")

        actions = ttk.Frame(body, style="SoftPanel.TFrame")
        actions.grid(row=6, column=0, sticky="ew", pady=(8, 0))
        self._grid_action_bar(
            actions,
            [
                ttk.Button(actions, text="添加配置", command=self._save_cloud_backend_from_form),
                ttk.Button(actions, text="刷新列表", command=self._refresh_cloud_backend_catalog),
                ttk.Button(actions, text="关闭", command=_close_window),
            ],
            columns=3,
        )

        footer = ttk.Frame(shell, style="Panel.TFrame", padding=(10, 12))
        footer.grid(row=2, column=0, sticky="ew", pady=(16, 0))
        footer.columnconfigure(0, weight=1)
        cloud_status_label = ttk.Label(footer, textvariable=self.cloud_status_var, style="Foot.TLabel", justify="left")
        cloud_status_label.grid(row=0, column=0, sticky="ew")
        self._register_adaptive_wrap_label(cloud_status_label, footer, padding=24, min_width=320, max_width=720)

        self._sync_cloud_provider_choices()
        self._refresh_cloud_backend_catalog()
        current_backend = self.backend_map.get(self.backend_combo.get(), self.backend_var.get() or "ollama")
        label = self.cloud_provider_reverse.get(current_backend)
        if label and self.cloud_provider_combo is not None:
            self.cloud_provider_combo.set(label)
            self._load_selected_cloud_backend_into_form()
        elif self.cloud_provider_combo is not None and self.cloud_provider_combo.get():
            self._load_selected_cloud_backend_into_form()

    def _process_queue(self) -> None:
        try:
            while True:
                status, name, payload = self.ui_queue.get_nowait()
                if status == "progress" and name == "startup":
                    normalized = self._normalize_startup_payload(payload)
                    self._set_startup_progress(
                        float(normalized.get("value", self.splash_progress_var.get())),
                        str(normalized.get("message") or self.splash_message_var.get()),
                        str(normalized.get("step") or self.splash_step_var.get().replace("当前步骤：", "", 1)),
                        str(normalized.get("detail") or self.splash_detail_var.get()),
                    )
                    continue
                if status == "progress" and name in {"self_check", "startup_self_check"}:
                    if self.runtime is not None:
                        self.runtime.update_local_task_progress(payload if isinstance(payload, dict) else {})
                        self._render_task_progress(self.runtime.get_task_progress_state())
                        self._render_logs(self.runtime.get_state().get("logs", []))
                    self.hero_var.set("后台准备中")
                    continue
                if status == "progress" and name == "task_progress_sync":
                    if isinstance(payload, dict):
                        local_task = dict(payload.get("local") or {})
                        if self.splash is not None and local_task:
                            local_percent = max(0.0, min(100.0, float(local_task.get("percent", 0.0) or 0.0)))
                            splash_value = 18.0 + (local_percent * 0.64)
                            splash_step = str(local_task.get("task_name") or local_task.get("title") or "启动自检").strip()
                            splash_detail = str(local_task.get("detail") or local_task.get("title") or "正在检查本机能力").strip()
                            self._set_startup_progress(splash_value, "正在执行启动自检", splash_step, splash_detail)
                        self._render_task_progress(payload)
                        if self.runtime is not None:
                            self._render_logs(self.runtime.get_state().get("logs", []))
                    continue
                if status == "error":
                    if name == "training_workspace":
                        self.training_annotation_workspace_pending = False
                    self.hero_var.set(f"{name} 失败: {payload}")
                    if self.splash is not None:
                        self.splash_message_var.set(f"初始化失败：{payload}")
                    self._log_gui_action("runtime_error", scope=name, detail=str(payload))
                    continue

                if name == "bootstrap":
                    bootstrap_payload = payload["payload"] if isinstance(payload, dict) and "payload" in payload else payload
                    self._apply_bootstrap_payload(bootstrap_payload)
                    self.hero_var.set("后台准备中")
                elif name == "refresh_models":
                    self.model_catalog = payload
                    self._update_model_choices()
                    self.hero_var.set("模型已刷新")
                elif name == "kb_catalog":
                    self.knowledge_catalog = payload
                    self._sync_knowledge_scope_choices()
                    self._populate_knowledge_tree()
                    self.hero_var.set("知识库已刷新")
                elif name == "kb_import":
                    kb_summary, kb_dialog = _format_kb_import_feedback(payload)
                    self.kb_status_var.set(kb_summary)
                    self.hero_var.set("知识库导入已完成")
                    self._render_logs(self.runtime.get_state().get("logs", []))
                    self._refresh_knowledge_bases()
                    self._refresh_expert_catalog()
                    self._log_gui_action("knowledge_import_done", detail=kb_dialog)
                elif name == "expert_catalog":
                    self.expert_catalog = payload
                    self._populate_expert_tree()
                    self.hero_var.set("专家已刷新")
                elif name == "expert_import":
                    self.expert_status_var.set(
                        f"导入完成: {payload['display_name']}，成功 {payload['imported_count']} 项，失败 {payload['failed_count']} 项"
                    )
                    self.hero_var.set("专家模型导入已完成")
                    self._refresh_expert_catalog()
                    self._log_gui_action(
                        "expert_import_done",
                        expert=payload["display_name"],
                        imported=payload["imported_count"],
                        failed=payload["failed_count"],
                        target_path=payload["target_path"],
                    )
                elif name == "cloud_catalog":
                    rows = list(payload)
                    for row in rows:
                        row["configured"] = bool(row.get("configured"))
                    self.cloud_backend_catalog = rows
                    self._sync_cloud_provider_choices()
                    self._load_selected_cloud_backend_into_form()
                    self.hero_var.set("模型服务配置已刷新")
                elif name == "cloud_save":
                    self.cloud_status_var.set(f"{payload['label']} 配置已保存")
                    self.hero_var.set("模型服务配置已保存")
                    if self.cloud_window is not None:
                        try:
                            if self.cloud_window.winfo_exists():
                                self.cloud_window.destroy()
                        except Exception:
                            pass
                        self.cloud_window = None
                    self._refresh_cloud_backend_catalog()
                    self._refresh_models()
                elif name == "self_check":
                    state_snapshot = self.runtime.get_state() if self.runtime is not None else None
                    if isinstance(state_snapshot, dict):
                        self._render_state(state_snapshot)
                    else:
                        self._render_checks(payload)
                        self._render_logs(self.runtime.get_state().get("logs", []))
                    local_task = (self.runtime.get_task_progress_state() or {}).get("local") if self.runtime is not None else {}
                    task_status = str((local_task or {}).get("status") or "").lower()
                    if task_status == "error":
                        self.hero_var.set("后台准备失败（已回退规则链）")
                    else:
                        self.hero_var.set("系统已可用")
                elif name == "startup_self_check":
                    state_snapshot = self.runtime.get_state() if self.runtime is not None else None
                    if isinstance(state_snapshot, dict):
                        self._render_state(state_snapshot)
                    else:
                        self._render_checks(payload)
                        self._render_logs(self.runtime.get_state().get("logs", []))
                    orchestrator_status = str(self.current_state.get("orchestrator", {}).get("status") or "").strip()
                    self.hero_var.set(_present_orchestrator_status(orchestrator_status))
                elif name == "orchestrator_prepare":
                    self._render_logs(self.runtime.get_state().get("logs", []))
                    status_text = str(payload.get("status") or "unknown")
                    reason_text = str(payload.get("reason") or "").strip()
                    self.hero_var.set(_present_orchestrator_status(status_text))
                    if reason_text:
                        self._log_gui_action("orchestrator_prepare_state", status=status_text, reason=reason_text)
                elif name == "voice_test":
                    level = str(payload.get("status") or "warn").lower()
                    summary = str(payload.get("summary") or "语音测试已结束")
                    detail = str(payload.get("detail") or "")
                    self.hero_var.set(summary)
                    dialog_text = f"{summary}\n\n{detail}".strip()
                    self._log_gui_action("voice_test_result", level=level, detail=dialog_text)
                elif name == "archive_catalog":
                    self.archive_catalog = list(payload)
                    self._populate_archive_tree()
                    self.hero_var.set("实验档案已刷新")
                elif name == "voice_local_action":
                    intent = str((payload or {}).get("intent") or "").strip() if isinstance(payload, dict) else ""
                    if intent:
                        try:
                            result = self._execute_voice_local_intent(intent)
                            if result is not None:
                                action_display, result_text = result
                                self._log_autonomy_action(action_display, target=intent, result_text=result_text)
                        except Exception as exc:
                            self._log_gui_action("voice_local_action_failed", intent=intent, error=str(exc))
                elif name == "training_overview":
                    self.training_overview = dict(payload)
                    self._render_training_overview()
                    self.training_status_var.set("训练概览已刷新")
                    self.hero_var.set("训练工作台已刷新")
                elif name == "training_workspace":
                    self.training_annotation_workspace_pending = False
                    workspace_dir = str(payload.get("workspace_dir") or "").strip()
                    if workspace_dir:
                        overview = dict(self.training_overview or {})
                        overview["latest_workspace"] = workspace_dir
                        self.training_overview = overview
                        self._render_training_overview()
                        if self.training_window is not None and self.training_window.winfo_exists():
                            self._refresh_training_annotation_panel()
                    self.training_status_var.set(f"训练工作区已生成: {payload['workspace_dir']}")
                    self.hero_var.set("训练工作区构建完成")
                    self._refresh_training_overview()
                elif name == "training_import_llm":
                    self.training_status_var.set(
                        f"LLM 数据导入完成: 新增 {payload['sample_count']} 条，总计 {payload['total_sample_count']} 条"
                    )
                    self.hero_var.set("LLM 训练数据导入完成")
                    self._refresh_training_overview()
                elif name == "training_import_pi":
                    self.training_status_var.set(
                        f"Pi 数据导入完成: 样本 {payload['sample_count']}，数据集文件 {payload['dataset_yaml']}"
                    )
                    self.hero_var.set("Pi 训练数据导入完成")
                    self._refresh_training_overview()
                elif name == "training_llm":
                    self.training_status_var.set(f"LLM 微调任务已启动: {payload['job_id']}")
                    self.hero_var.set("LLM 微调已启动")
                    self._refresh_training_overview()
                elif name == "training_pi":
                    self.training_status_var.set(f"Pi 微调任务已启动: {payload['job_id']}")
                    self.hero_var.set("Pi 微调已启动")
                    self._refresh_training_overview()
                elif name == "training_all":
                    self.training_status_var.set(f"一键全流程训练任务已启动: {payload['job_id']}")
                    self.hero_var.set("一键训练已启动")
                    self._refresh_training_overview()
                elif name in {"start_session", "stop_session"}:
                    self._render_state(payload)
                    if name == "stop_session":
                        self.hero_var.set("系统已可用")
                        self._render_node_logs([])
                    if self.archive_window is not None:
                        self._refresh_archive_catalog()
        except queue.Empty:
            pass
        self.root.after(250, self._process_queue)

    def _on_close(self) -> None:
        self.is_closing = True
        try:
            if self.resize_after_id is not None:
                try:
                    self.root.after_cancel(self.resize_after_id)
                except Exception:
                    pass
                self.resize_after_id = None
            if self.stream_refresh_after_id is not None:
                try:
                    self.root.after_cancel(self.stream_refresh_after_id)
                except Exception:
                    pass
                self.stream_refresh_after_id = None
            if self.window_state_after_id is not None:
                try:
                    self.root.after_cancel(self.window_state_after_id)
                except Exception:
                    pass
                self.window_state_after_id = None
            if self.tooltip_after_id is not None:
                try:
                    self.root.after_cancel(self.tooltip_after_id)
                except Exception:
                    pass
                self.tooltip_after_id = None
            for window in list(self.window_refs):
                try:
                    window.destroy()
                except Exception:
                    pass
            if self.splash is not None:
                try:
                    self.splash.destroy()
                except Exception:
                    pass
            self._save_window_state()
            if self.runtime is not None:
                self.runtime.shutdown()
        finally:
            self._hide_tooltip()
            self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def launch_desktop_app(open_training_workbench: bool = False, training_focus: str = "") -> int:
    app = DesktopApp()
    if open_training_workbench:
        def _open_training_window_when_ready() -> None:
            if app.runtime is None:
                app.root.after(300, _open_training_window_when_ready)
                return
            app._show_training_window(training_focus)

        app.root.after(1200, _open_training_window_when_ready)
    app.run()
    return 0
