#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Desktop visualization app for LabDetector."""

from __future__ import annotations

import ctypes
import json
import queue
import re
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, Callable, Dict, List

import cv2
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
from pc.webui.runtime import LabDetectorRuntime


class DesktopApp:
    def __init__(self) -> None:
        self._enable_dpi_awareness()
        self.runtime = LabDetectorRuntime()
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title(f"{APP_DISPLAY_NAME} v{self.runtime.version}")
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
        self.expert_catalog: List[Dict[str, Any]] = []
        self.expert_window: tk.Toplevel | None = None
        self.expert_tree: ttk.Treeview | None = None
        self.expert_detail_text: tk.Text | None = None
        self.expert_status_var = tk.StringVar(value="等待加载专家模型目录")
        self.cloud_backend_catalog: List[Dict[str, Any]] = []
        self.cloud_window: tk.Toplevel | None = None
        self.cloud_provider_combo: ttk.Combobox | None = None
        self.cloud_provider_map: Dict[str, str] = {}
        self.cloud_provider_reverse: Dict[str, str] = {}
        self.cloud_api_key_entry: ttk.Entry | None = None
        self.cloud_base_url_entry: ttk.Entry | None = None
        self.cloud_model_entry: ttk.Entry | None = None
        self.cloud_status_var = tk.StringVar(value="等待配置云模型 API")
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
        self.log_text: tk.Text | None = None
        self.session_badge: tk.Label | None = None
        self.hero_message_label: ttk.Label | None = None
        self.info_description_label: ttk.Label | None = None
        self.info_copyright_label: ttk.Label | None = None
        self.resize_after_id: str | None = None
        self.window_state_after_id: str | None = None
        self.tooltip_window: tk.Toplevel | None = None
        self.tooltip_after_id: str | None = None
        self.demo_restore_geometry: str | None = None
        self.demo_restore_state: str = "normal"
        self.demo_restore_collapsed: bool = False
        self.scroll_routes: Dict[str, Dict[str, Any]] = {}
        self.hidden_demo_enabled = bool(get_config("shadow_demo.enabled", False))
        self.current_state: Dict[str, Any] = {
            "summary": {},
            "session": {},
            "streams": [],
            "self_check": [],
            "logs": [],
        }

        self.backend_var = tk.StringVar()
        self.model_var = tk.StringVar()
        self.custom_model_var = tk.StringVar()
        self.mode_var = tk.StringVar(value="camera")
        self.expected_nodes_var = tk.StringVar(value="1")
        self.hero_var = tk.StringVar(value="正在初始化可视化界面")
        self.session_var = tk.StringVar(value="待机")
        self.brand_var = tk.StringVar(value=f"{COMPANY_NAME} | 版本 v{self.runtime.version}")
        self.footer_var = tk.StringVar(value=COPYRIGHT_TEXT)
        self.splash_message_var = tk.StringVar(value="正在准备运行环境与监控界面…")
        self.kb_status_var = tk.StringVar(value="等待载入知识库目录")
        self.kb_reset_var = tk.BooleanVar(value=False)
        self.kb_structured_var = tk.BooleanVar(value=True)
        self.left_collapsed_var = tk.BooleanVar(value=False)
        self.demo_mode_var = tk.BooleanVar(value=False)

        self.summary_vars = {
            "mode": tk.StringVar(value="-"),
            "online": tk.StringVar(value="0"),
            "offline": tk.StringVar(value="0"),
            "voice": tk.StringVar(value="OFF"),
        }
        self.hero_var.set("正在初始化桌面可视化界面")
        self.session_var.set("待机")
        self.brand_var.set(f"{COMPANY_NAME} | 版本 v{self.runtime.version}")
        self.splash_message_var.set("正在准备运行环境与监控界面…")
        self.kb_status_var.set("等待载入知识库目录")

        self._build_style()
        self._apply_branding()
        self._build_menu()
        self._build_layout()
        self._restore_window_state()
        self._show_startup_splash()
        self._bind_events()
        self._load_bootstrap()

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(250, self._process_queue)
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
        style.configure("Header.TLabel", background="#182330", foreground="#f5f7fb", font=("Microsoft YaHei UI", 24, "bold"))
        style.configure("Body.TLabel", background="#182330", foreground="#d7e0ea", font=("Microsoft YaHei UI", 10))
        style.configure("Brand.TLabel", background="#182330", foreground="#78e6ff", font=("Microsoft YaHei UI", 10, "bold"))
        style.configure("PanelTitle.TLabel", background="#182330", foreground="#f5f7fb", font=("Microsoft YaHei UI", 13, "bold"))
        style.configure("MetricValue.TLabel", background="#243548", foreground="#ffffff", font=("Bahnschrift", 24, "bold"))
        style.configure("MetricLabel.TLabel", background="#243548", foreground="#c3d0dc", font=("Microsoft YaHei UI", 10))
        style.configure("Foot.TLabel", background="#182330", foreground="#9fb6c9", font=("Microsoft YaHei UI", 9))
        style.configure("SplashTitle.TLabel", background="#0b1e2d", foreground="#ffffff", font=("Microsoft YaHei UI", 28, "bold"))
        style.configure("SplashBody.TLabel", background="#0b1e2d", foreground="#d6e6f2", font=("Microsoft YaHei UI", 11))
        style.configure("TButton", font=("Microsoft YaHei UI", 10), padding=(self._scaled(10), self._scaled(8)))
        style.configure("Accent.TButton", font=("Microsoft YaHei UI", 10, "bold"), padding=(self._scaled(10), self._scaled(8)))
        style.configure("TCombobox", padding=self._scaled(6))
        style.configure(
            "Treeview",
            rowheight=self._scaled(30),
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

    def _build_menu(self) -> None:
        menubar = tk.Menu(self.root, tearoff=False, bg="#182330", fg="#f5f7fb", activebackground="#20c997", activeforeground="#0f1720")
        software_menu = tk.Menu(menubar, tearoff=False, bg="#182330", fg="#f5f7fb", activebackground="#20c997", activeforeground="#0f1720")
        software_menu.add_command(label="运行启动自检", command=self._run_self_check)
        software_menu.add_command(label="刷新模型", command=self._refresh_models)
        software_menu.add_command(label="知识库管理", command=self._show_knowledge_base_window)
        software_menu.add_separator()
        software_menu.add_command(label="退出", command=self._on_close)

        view_menu = tk.Menu(menubar, tearoff=False, bg="#182330", fg="#f5f7fb", activebackground="#20c997", activeforeground="#0f1720")
        view_menu.add_command(label="折叠 / 展开左栏", command=self._toggle_left_panel)
        view_menu.add_command(label="恢复默认布局", command=self._reset_window_layout)

        help_menu = tk.Menu(menubar, tearoff=False, bg="#182330", fg="#f5f7fb", activebackground="#20c997", activeforeground="#0f1720")
        help_menu.add_command(label="软件说明", command=self._show_manual_window)
        help_menu.add_command(label="关于软件", command=self._show_about_window)
        help_menu.add_command(label="版权信息", command=self._show_copyright_window)

        menubar.add_cascade(label="软件", menu=software_menu)
        menubar.add_cascade(label="视图", menu=view_menu)
        menubar.add_cascade(label="帮助", menu=help_menu)
        self.root.configure(menu=menubar)

    def _build_layout(self) -> None:
        shell = ttk.Frame(self.root, style="Root.TFrame", padding=18)
        shell.pack(fill="both", expand=True)
        shell.columnconfigure(0, weight=0, minsize=self.left_panel_width)
        shell.columnconfigure(1, weight=1)
        shell.rowconfigure(1, weight=1)
        shell.rowconfigure(2, weight=1)
        self.shell_frame = shell

        hero = ttk.Frame(shell, style="Panel.TFrame", padding=20)
        hero.grid(row=0, column=0, columnspan=2, sticky="nsew", pady=(0, 16))
        hero.columnconfigure(0, weight=1)
        hero.columnconfigure(1, weight=0)

        hero_left = ttk.Frame(hero, style="Panel.TFrame")
        hero_left.grid(row=0, column=0, sticky="w")
        ttk.Label(hero_left, text=APP_DISPLAY_NAME, style="Header.TLabel").pack(anchor="w")
        ttk.Label(hero_left, text=APP_SHORT_TAGLINE, style="Brand.TLabel").pack(anchor="w", pady=(6, 0))
        self.hero_message_label = ttk.Label(hero_left, textvariable=self.hero_var, style="Body.TLabel", wraplength=self.hero_wraplength)
        self.hero_message_label.pack(anchor="w", pady=(8, 0))
        ttk.Label(hero_left, textvariable=self.brand_var, style="Foot.TLabel").pack(anchor="w", pady=(10, 0))

        hero_right = ttk.Frame(hero, style="Panel.TFrame")
        hero_right.grid(row=0, column=1, sticky="e")
        self.session_badge = tk.Label(hero_right, textvariable=self.session_var, bg="#1fb68d", fg="#0f1720", font=("Microsoft YaHei UI", 11, "bold"), padx=14, pady=8)
        self.session_badge.pack(anchor="e")
        ttk.Button(hero_right, text="\u6298\u53e0 / \u5c55\u5f00\u5de6\u680f", command=self._toggle_left_panel).pack(anchor="e", pady=(10, 0), fill="x")
        ttk.Button(hero_right, text="运行启动自检", command=self._run_self_check).pack(anchor="e", pady=(8, 0), fill="x")
        ttk.Button(hero_right, text="专家模型管理", command=self._show_expert_window).pack(anchor="e", pady=(8, 0), fill="x")
        ttk.Button(hero_right, text="知识库管理", command=self._show_knowledge_base_window).pack(anchor="e", pady=(8, 0), fill="x")
        ttk.Button(hero_right, text="云模型配置", command=self._show_cloud_backend_window).pack(anchor="e", pady=(8, 0), fill="x")
        ttk.Button(hero_right, text="软件说明", command=self._show_manual_window).pack(anchor="e", pady=(8, 0), fill="x")
        ttk.Button(hero_right, text="关于 / 版权", command=self._show_about_and_copyright).pack(anchor="e", pady=(8, 0), fill="x")

        left = ttk.Frame(shell, style="Panel.TFrame", padding=18)
        left.grid(row=1, column=0, rowspan=2, sticky="nsew", padx=(0, 16))
        left.configure(width=self.left_panel_width)
        left.grid_propagate(False)
        left.columnconfigure(0, weight=1)
        left.rowconfigure(0, weight=1)
        self.left_panel = left

        self.left_canvas = tk.Canvas(left, bg="#182330", highlightthickness=0)
        self.left_canvas.grid(row=0, column=0, sticky="nsew")
        left_scroll = ttk.Scrollbar(left, orient="vertical", command=self.left_canvas.yview)
        left_scroll.grid(row=0, column=1, sticky="ns")
        self.left_canvas.configure(yscrollcommand=left_scroll.set)
        self.left_inner = ttk.Frame(self.left_canvas, style="Panel.TFrame")
        self.left_window = self.left_canvas.create_window((0, 0), window=self.left_inner, anchor="nw")
        self.left_inner.columnconfigure(0, weight=1)
        self.left_inner.bind("<Configure>", self._on_left_inner_configure)
        self.left_canvas.bind("<Configure>", self._on_left_canvas_configure)

        config_panel = ttk.Frame(self.left_inner, style="SoftPanel.TFrame", padding=16)
        config_panel.grid(row=0, column=0, sticky="ew")
        config_panel.columnconfigure(0, weight=1)
        ttk.Label(config_panel, text="运行配置", style="PanelTitle.TLabel").grid(row=0, column=0, sticky="w")

        self.form = ttk.Frame(config_panel, style="SoftPanel.TFrame")
        self.form.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        self.form.columnconfigure(0, weight=1)

        self.backend_combo = self._add_labeled_combo(self.form, 0, "AI 后端")
        self.model_combo = self._add_labeled_combo(self.form, 1, "模型预设")
        self.custom_entry = self._add_labeled_entry(self.form, 2, "自定义模型")
        self.mode_combo = self._add_labeled_combo(self.form, 3, "运行模式")
        self.expected_entry = self._add_labeled_entry(self.form, 4, "预期节点数")

        btn_row = ttk.Frame(config_panel, style="SoftPanel.TFrame")
        btn_row.grid(row=2, column=0, sticky="ew", pady=(14, 0))
        btn_row.columnconfigure(0, weight=1)
        btn_row.columnconfigure(1, weight=1)
        ttk.Button(btn_row, text="刷新模型", command=self._refresh_models).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ttk.Button(btn_row, text="启动监控", style="Accent.TButton", command=self._start_session).grid(row=0, column=1, sticky="ew", padx=(6, 0))
        ttk.Button(config_panel, text="停止监控", command=self._stop_session).grid(row=3, column=0, sticky="ew", pady=(10, 0))

        summary_panel = ttk.Frame(self.left_inner, style="SoftPanel.TFrame", padding=16)
        summary_panel.grid(row=1, column=0, sticky="ew", pady=(16, 0))
        ttk.Label(summary_panel, text="运行概览", style="PanelTitle.TLabel").pack(anchor="w")
        self.summary_frame = ttk.Frame(summary_panel, style="SoftPanel.TFrame")
        self.summary_frame.pack(fill="x", pady=(12, 0))

        checks_panel = ttk.Frame(self.left_inner, style="SoftPanel.TFrame", padding=16)
        checks_panel.grid(row=2, column=0, sticky="ew", pady=(16, 0))
        checks_panel.columnconfigure(0, weight=1)
        checks_panel.rowconfigure(1, weight=1)
        ttk.Label(checks_panel, text="启动自检结果", style="PanelTitle.TLabel").grid(row=0, column=0, sticky="w")

        self.check_tree = ttk.Treeview(checks_panel, columns=("status", "summary"), show="headings", height=7)
        self.check_tree.heading("status", text="状态")
        self.check_tree.heading("summary", text="摘要")
        self.check_tree.column("status", width=80, anchor="center")
        self.check_tree.column("summary", width=260, anchor="w")
        self.check_tree.grid(row=1, column=0, sticky="nsew", pady=(12, 0))

        info_panel = ttk.Frame(self.left_inner, style="SoftPanel.TFrame", padding=16)
        info_panel.grid(row=3, column=0, sticky="ew", pady=(16, 0))
        ttk.Label(info_panel, text="软件信息", style="PanelTitle.TLabel").pack(anchor="w")
        self.info_description_label = ttk.Label(info_panel, text=APP_DESCRIPTION, style="Body.TLabel", wraplength=self.info_wraplength)
        self.info_description_label.pack(anchor="w", pady=(10, 0))
        self.info_copyright_label = ttk.Label(info_panel, text=COPYRIGHT_TEXT, style="Foot.TLabel", wraplength=self.info_wraplength)
        self.info_copyright_label.pack(anchor="w", pady=(10, 0))

        right_top = ttk.Frame(shell, style="Panel.TFrame", padding=18)
        right_top.grid(row=1, column=1, sticky="nsew")
        right_top.columnconfigure(0, weight=1)
        right_top.rowconfigure(1, weight=1)
        ttk.Label(right_top, text="节点监控墙", style="PanelTitle.TLabel").grid(row=0, column=0, sticky="w")

        self.wall_canvas = tk.Canvas(right_top, bg="#182330", highlightthickness=0)
        self.wall_canvas.grid(row=1, column=0, sticky="nsew", pady=(12, 0))
        wall_scroll = ttk.Scrollbar(right_top, orient="vertical", command=self.wall_canvas.yview)
        wall_scroll.grid(row=1, column=1, sticky="ns", pady=(12, 0))
        self.wall_canvas.configure(yscrollcommand=wall_scroll.set)

        self.wall_inner = ttk.Frame(self.wall_canvas, style="Panel.TFrame")
        self.wall_window = self.wall_canvas.create_window((0, 0), window=self.wall_inner, anchor="nw")
        self.wall_inner.bind("<Configure>", self._on_wall_configure)
        self.wall_canvas.bind("<Configure>", self._on_canvas_configure)

        right_bottom = ttk.Frame(shell, style="Panel.TFrame", padding=18)
        right_bottom.grid(row=2, column=1, sticky="nsew", pady=(16, 0))
        right_bottom.columnconfigure(0, weight=1)
        right_bottom.rowconfigure(1, weight=1)
        ttk.Label(right_bottom, text="提示信息与运行日志", style="PanelTitle.TLabel").grid(row=0, column=0, sticky="w")

        self.log_text = tk.Text(right_bottom, height=10, bg="#0f1720", fg="#dbe6f2", insertbackground="#dbe6f2", relief="flat", font=("Consolas", 10), wrap="word")
        self.log_text.grid(row=1, column=0, sticky="nsew", pady=(12, 0))
        self.log_text.configure(state="disabled")

        footer = ttk.Frame(shell, style="Panel.TFrame", padding=(20, 10))
        footer.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(16, 0))
        footer.columnconfigure(0, weight=1)
        ttk.Label(footer, textvariable=self.footer_var, style="Foot.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(footer, text=f"{COMPANY_NAME} | v{self.runtime.version}", style="Foot.TLabel").grid(row=0, column=1, sticky="e")

        self._register_scroll_target(self.left_canvas, self.left_canvas)
        self._register_scroll_target(self.left_inner, self.left_canvas)
        self._register_scroll_target(self.wall_canvas, self.wall_canvas)
        self._register_scroll_target(self.wall_inner, self.wall_canvas)
        self._register_scroll_target(self.log_text, self.log_text)
        self._register_scroll_target(self.check_tree, self.check_tree)

    def _show_startup_splash(self) -> None:
        splash = tk.Toplevel(self.root)
        splash.overrideredirect(True)
        splash.configure(bg="#071018")
        splash.attributes("-topmost", True)
        self.splash = splash

        width = min(self.window_width - self._scaled(120), self._scaled(760))
        height = min(self.window_height - self._scaled(140), self._scaled(420))
        screen_w = splash.winfo_screenwidth()
        screen_h = splash.winfo_screenheight()
        offset_x = int((screen_w - width) / 2)
        offset_y = int((screen_h - height) / 2)
        splash.geometry(f"{width}x{height}+{offset_x}+{offset_y}")

        panel = ttk.Frame(splash, style="Panel.TFrame", padding=24)
        panel.pack(fill="both", expand=True)
        panel.columnconfigure(0, weight=0)
        panel.columnconfigure(1, weight=1)

        logo_holder = ttk.Frame(panel, style="Panel.TFrame")
        logo_holder.grid(row=0, column=0, sticky="nsw", padx=(0, 24))
        self.splash_logo_image = self._load_logo_image((160, 160))
        if self.splash_logo_image is not None:
            tk.Label(logo_holder, image=self.splash_logo_image, bg="#182330").pack(anchor="w", pady=(14, 0))
        else:
            tk.Label(logo_holder, text="LD", bg="#0b1e2d", fg="#78e6ff", font=("Bahnschrift", 40, "bold"), padx=36, pady=42).pack(anchor="w", pady=(14, 0))

        text_holder = ttk.Frame(panel, style="Panel.TFrame")
        text_holder.grid(row=0, column=1, sticky="nsew")
        ttk.Label(text_holder, text=APP_DISPLAY_NAME, style="SplashTitle.TLabel").pack(anchor="w", pady=(18, 0))
        ttk.Label(text_holder, text=APP_SHORT_TAGLINE, style="Brand.TLabel").pack(anchor="w", pady=(10, 0))
        ttk.Label(text_holder, text=f"{COMPANY_NAME} | 版本 v{self.runtime.version}", style="SplashBody.TLabel").pack(anchor="w", pady=(10, 0))
        wraplength = max(self._scaled(360), width - self._scaled(320))
        ttk.Label(text_holder, textvariable=self.splash_message_var, style="SplashBody.TLabel", wraplength=wraplength).pack(anchor="w", pady=(18, 0))
        ttk.Label(text_holder, text=COPYRIGHT_TEXT, style="Foot.TLabel", wraplength=wraplength).pack(anchor="w", pady=(18, 0))

        progress = ttk.Progressbar(text_holder, mode="indeterminate", length=min(self._scaled(360), wraplength))
        progress.pack(anchor="w", pady=(22, 0))
        progress.start(12)
        splash.update_idletasks()

    def _load_logo_image(self, size: tuple[int, int]) -> ImageTk.PhotoImage | None:
        try:
            logo_file = logo_path()
            if not logo_file.exists():
                return None
            return ImageTk.PhotoImage(Image.open(logo_file).resize(size, Image.Resampling.LANCZOS))
        except Exception:
            return None

    def _finish_startup(self) -> None:
        if self.splash is not None:
            try:
                self.splash.destroy()
            except Exception:
                pass
            self.splash = None
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

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

    def _bind_events(self) -> None:
        self.backend_combo.bind("<<ComboboxSelected>>", lambda _event: self._update_model_choices())
        self.model_combo.bind("<<ComboboxSelected>>", lambda _event: self._sync_field_visibility())
        self.mode_combo.bind("<<ComboboxSelected>>", lambda _event: self._sync_field_visibility())
        self.root.bind("<Configure>", self._on_root_configure)
        self.root.bind("<F11>", lambda _event: self._toggle_demo_mode())
        self.root.bind("<Escape>", lambda _event: self._handle_escape_key())
        self._bind_global_scroll_support()

    def _load_bootstrap(self) -> None:
        payload = self.runtime.bootstrap()
        controls = payload["controls"]
        self.backend_combo["values"] = [item["label"] for item in controls["backends"]]
        self.backend_map = {item["label"]: item["value"] for item in controls["backends"]}
        self.backend_reverse = {value: label for label, value in self.backend_map.items()}
        self.mode_combo["values"] = [item["label"] for item in controls["modes"]]
        self.mode_map = {item["label"]: item["value"] for item in controls["modes"]}
        self.mode_reverse = {value: label for label, value in self.mode_map.items()}
        self.model_catalog = controls["models"]
        self.knowledge_catalog = payload.get("knowledge_bases", [])
        self._sync_knowledge_scope_choices()

        self.backend_var.set(controls["defaults"]["ai_backend"])
        self.mode_var.set(controls["defaults"]["mode"])
        self.backend_combo.set(self.backend_reverse[self.backend_var.get()])
        self.mode_combo.set(self.mode_reverse[self.mode_var.get()])
        self.expected_nodes_var.set(str(controls["defaults"]["expected_nodes"]))
        self.expected_entry.delete(0, tk.END)
        self.expected_entry.insert(0, self.expected_nodes_var.get())

        self._update_model_choices(controls["defaults"]["selected_model"])
        self.current_state = payload["state"]
        self._render_summary(payload["state"])
        self._render_checks(payload["state"]["self_check"])
        self._render_logs(payload["state"]["logs"])
        self._render_streams(payload["state"]["streams"])
        self.splash_message_var.set("基础环境加载完成，正在进入主界面…")
        self.root.after(450, self._finish_startup)

    def _update_model_choices(self, selected_model: str | None = None) -> None:
        backend_value = self.backend_map.get(self.backend_combo.get(), self.backend_var.get() or "ollama")
        self.backend_var.set(backend_value)
        models = list(self.model_catalog.get(backend_value, []))
        if "自定义模型" not in models:
            models.append("自定义模型")
        self.model_combo["values"] = models
        desired = selected_model or (models[0] if models else "自定义模型")
        if desired not in models:
            self.model_combo.set("自定义模型")
            self.custom_model_var.set(desired)
            self.custom_entry.delete(0, tk.END)
            self.custom_entry.insert(0, desired)
        else:
            self.model_combo.set(desired)
            if desired != "自定义模型":
                self.custom_entry.delete(0, tk.END)
        self._sync_field_visibility()

    def _sync_field_visibility(self) -> None:
        is_custom = self.model_combo.get() == "自定义模型"
        is_multi = self.mode_map.get(self.mode_combo.get(), self.mode_var.get()) == "websocket"
        self.custom_entry.master.grid() if is_custom else self.custom_entry.master.grid_remove()
        self.expected_entry.master.grid() if is_multi else self.expected_entry.master.grid_remove()

    def _dispatch(self, name: str, fn) -> None:
        def runner() -> None:
            try:
                result = fn()
                self.ui_queue.put(("ok", name, result))
            except Exception as exc:
                self.ui_queue.put(("error", name, str(exc)))

        threading.Thread(target=runner, daemon=True, name=f"UI_{name}").start()

    def _refresh_models(self) -> None:
        self.hero_var.set("正在刷新模型清单")
        self._dispatch("refresh_models", self.runtime.refresh_model_catalog)

    def _sync_knowledge_scope_choices(self) -> None:
        labels = []
        self.kb_scope_map = {}
        self.kb_scope_reverse = {}
        for row in self.knowledge_catalog:
            label = f"{row['title']} [{row['scope']}]"
            labels.append(label)
            self.kb_scope_map[label] = row["scope"]
            self.kb_scope_reverse[row["scope"]] = label
        if not labels:
            labels = ["公共底座知识库 [common]"]
            self.kb_scope_map = {labels[0]: "common"}
            self.kb_scope_reverse = {"common": labels[0]}
        if self.kb_scope_combo is not None:
            self.kb_scope_combo["values"] = labels
            if not self.kb_scope_combo.get():
                self.kb_scope_combo.set(labels[0])

    def _selected_kb_scope(self) -> str:
        if self.kb_scope_combo is None:
            return "common"
        return self.kb_scope_map.get(self.kb_scope_combo.get(), "common")

    def _refresh_knowledge_bases(self) -> None:
        self.hero_var.set("正在刷新知识库目录")
        self._dispatch("kb_catalog", self.runtime.get_knowledge_base_catalog)

    def _import_knowledge_files(self) -> None:
        paths = filedialog.askopenfilenames(
            parent=self.kb_window or self.root,
            title="选择要导入的知识文件",
            filetypes=[
                ("Knowledge Files", "*.txt *.md *.csv *.json *.xls *.xlsx"),
                ("Text Files", "*.txt *.md"),
                ("Table Files", "*.csv *.xls *.xlsx"),
                ("JSON Files", "*.json"),
                ("All Files", "*.*"),
            ],
        )
        if not paths:
            return
        scope = self._selected_kb_scope()
        self.kb_status_var.set(f"正在导入 {len(paths)} 个知识文件到 {scope}")
        self.hero_var.set("正在导入知识文件")
        self._dispatch(
            "kb_import",
            lambda: self.runtime.import_knowledge_paths(
                list(paths),
                scope_name=scope,
                reset_index=bool(self.kb_reset_var.get()),
                structured=bool(self.kb_structured_var.get()),
            ),
        )

    def _import_knowledge_folder(self) -> None:
        directory = filedialog.askdirectory(parent=self.kb_window or self.root, title="选择知识库文件夹")
        if not directory:
            return
        scope = self._selected_kb_scope()
        self.kb_status_var.set(f"正在导入目录 {directory} 到 {scope}")
        self.hero_var.set("正在导入知识目录")
        self._dispatch(
            "kb_import",
            lambda: self.runtime.import_knowledge_paths(
                [directory],
                scope_name=scope,
                reset_index=bool(self.kb_reset_var.get()),
                structured=bool(self.kb_structured_var.get()),
            ),
        )

    def _render_kb_detail(self, row: Dict[str, Any]) -> None:
        if self.kb_detail_text is None:
            return
        docs = row.get("docs") or []
        lines = [
            f"作用域: {row.get('scope', '')}",
            f"标题: {row.get('title', '')}",
            f"文档数量: {row.get('doc_count', 0)}",
            f"向量索引: {'是' if row.get('vector_ready') else '否'}",
            f"结构化库: {'是' if row.get('structured_ready') else '否'}",
            f"文档目录: {row.get('docs_dir', '')}",
            f"向量目录: {row.get('vector_path', '')}",
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
        selected = self.kb_tree.selection()
        if not selected:
            return
        scope = selected[0]
        for row in self.knowledge_catalog:
            if row["scope"] == scope:
                self._render_kb_detail(row)
                break

    def _populate_knowledge_tree(self) -> None:
        if self.kb_tree is None:
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
                    "是" if row.get("vector_ready") else "否",
                    "是" if row.get("structured_ready") else "否",
                ),
            )
        if self.knowledge_catalog:
            first_scope = self.knowledge_catalog[0]["scope"]
            self.kb_tree.selection_set(first_scope)
            self._render_kb_detail(self.knowledge_catalog[0])
            if self.kb_scope_combo is not None:
                self.kb_scope_combo.set(self.kb_scope_reverse.get(first_scope, self.kb_scope_combo.get()))
        self.kb_status_var.set(f"已加载 {len(self.knowledge_catalog)} 个知识库作用域")

    def _show_knowledge_base_window(self) -> None:
        if self.kb_window is not None and self.kb_window.winfo_exists():
            self.kb_window.deiconify()
            self.kb_window.lift()
            self.kb_window.focus_force()
            self._refresh_knowledge_bases()
            return

        window = tk.Toplevel(self.root)
        window.title(f"{APP_DISPLAY_NAME} - 知识库管理")
        self._set_window_geometry(window, min(1180, int(self.window_width * 0.72)), min(820, int(self.window_height * 0.8)), 900, 620)
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
        ttk.Label(header, text="公共底座知识库 + 专家专属知识库统一导入与查看", style="Body.TLabel").grid(row=1, column=0, sticky="w", pady=(8, 0))

        control = ttk.Frame(shell, style="Panel.TFrame", padding=16)
        control.grid(row=1, column=0, sticky="nsew", pady=(16, 0))
        control.columnconfigure(0, weight=3)
        control.columnconfigure(1, weight=2)
        control.rowconfigure(1, weight=1)

        topbar = ttk.Frame(control, style="SoftPanel.TFrame", padding=12)
        topbar.grid(row=0, column=0, columnspan=2, sticky="ew")
        topbar.columnconfigure(1, weight=1)
        ttk.Label(topbar, text="导入目标", style="Body.TLabel").grid(row=0, column=0, sticky="w")
        self.kb_scope_combo = ttk.Combobox(topbar, state="readonly")
        self.kb_scope_combo.grid(row=0, column=1, sticky="ew", padx=(10, 12))
        ttk.Checkbutton(topbar, text="导入前重建当前作用域索引", variable=self.kb_reset_var).grid(row=0, column=2, sticky="w", padx=(0, 10))
        ttk.Checkbutton(topbar, text="同步写入结构化知识库", variable=self.kb_structured_var).grid(row=0, column=3, sticky="w", padx=(0, 10))
        ttk.Button(topbar, text="导入文件", command=self._import_knowledge_files).grid(row=0, column=4, sticky="ew", padx=(0, 8))
        ttk.Button(topbar, text="导入文件夹", command=self._import_knowledge_folder).grid(row=0, column=5, sticky="ew", padx=(0, 8))
        ttk.Button(topbar, text="刷新目录", command=self._refresh_knowledge_bases).grid(row=0, column=6, sticky="ew")

        table_wrap = ttk.Frame(control, style="SoftPanel.TFrame", padding=12)
        table_wrap.grid(row=1, column=0, sticky="nsew", pady=(14, 0), padx=(0, 10))
        table_wrap.columnconfigure(0, weight=1)
        table_wrap.rowconfigure(0, weight=1)

        self.kb_tree = ttk.Treeview(table_wrap, columns=("scope", "title", "docs", "vector", "structured"), show="headings")
        self.kb_tree.heading("scope", text="作用域")
        self.kb_tree.heading("title", text="名称")
        self.kb_tree.heading("docs", text="文件数")
        self.kb_tree.heading("vector", text="向量索引")
        self.kb_tree.heading("structured", text="结构化库")
        self.kb_tree.column("scope", width=220, anchor="w")
        self.kb_tree.column("title", width=260, anchor="w")
        self.kb_tree.column("docs", width=80, anchor="center")
        self.kb_tree.column("vector", width=90, anchor="center")
        self.kb_tree.column("structured", width=90, anchor="center")
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
        ttk.Label(footer, textvariable=self.kb_status_var, style="Foot.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Button(footer, text="关闭", command=_close_window).grid(row=0, column=1, sticky="e")

        self._sync_knowledge_scope_choices()
        if self.kb_scope_combo["values"]:
            self.kb_scope_combo.set(self.kb_scope_combo["values"][0])
        self._populate_knowledge_tree()
        self._refresh_knowledge_bases()

    def _run_self_check(self) -> None:
        self.hero_var.set("正在执行 5 项启动自检")
        self._dispatch("self_check", self.runtime.run_self_check)

    def _start_session(self) -> None:
        try:
            expected_nodes = int(self.expected_entry.get().strip() or "1")
        except ValueError:
            messagebox.showerror(APP_DISPLAY_NAME, "预期节点数必须为整数。", parent=self.root)
            return

        backend_value = self.backend_map.get(self.backend_combo.get(), "ollama")
        mode_value = self.mode_map.get(self.mode_combo.get(), "camera")
        selected_model = self.model_combo.get()
        custom_model = self.custom_entry.get().strip() if selected_model == "自定义模型" else ""
        payload = {
            "ai_backend": backend_value,
            "selected_model": "" if selected_model == "自定义模型" else selected_model,
            "custom_model": custom_model,
            "mode": mode_value,
            "expected_nodes": max(expected_nodes, 1),
        }
        self.hero_var.set("正在启动监控会话")
        self._dispatch("start_session", lambda: self.runtime.start_session(payload))

    def _stop_session(self) -> None:
        self.hero_var.set("正在停止监控会话")
        self._dispatch("stop_session", self.runtime.stop_session)

    def _process_queue(self) -> None:
        try:
            while True:
                status, name, payload = self.ui_queue.get_nowait()
                if status == "error":
                    self.hero_var.set(f"{name} 失败: {payload}")
                    if self.splash is not None:
                        self.splash_message_var.set(f"初始化失败：{payload}")
                    messagebox.showerror(APP_DISPLAY_NAME, str(payload), parent=self.root)
                    continue

                if name == "refresh_models":
                    self.model_catalog = payload
                    self._update_model_choices()
                    self.hero_var.set("模型清单已刷新")
                elif name == "kb_catalog":
                    self.knowledge_catalog = payload
                    self._sync_knowledge_scope_choices()
                    self._populate_knowledge_tree()
                    self.hero_var.set("知识库目录已刷新")
                elif name == "kb_import":
                    self.kb_status_var.set(
                        f"导入完成: 作用域={payload['scope']}，成功 {payload['imported_count']} 项，失败 {payload['failed_count']} 项"
                    )
                    self.hero_var.set("知识库导入已完成")
                    self._render_logs(self.runtime.get_state().get("logs", []))
                    messagebox.showinfo(
                        APP_DISPLAY_NAME,
                        f"作用域: {payload['scope']}\n成功: {payload['imported_count']}\n失败: {payload['failed_count']}\n结构化记录: {payload.get('structured_records', 0)}",
                        parent=self.kb_window or self.root,
                    )
                    self._refresh_knowledge_bases()
                elif name == "self_check":
                    self._render_checks(payload)
                    self._render_logs(self.runtime.get_state().get("logs", []))
                    self.hero_var.set("启动自检已完成")
                elif name in {"start_session", "stop_session"}:
                    self._render_state(payload)
        except queue.Empty:
            pass
        self.root.after(250, self._process_queue)

    def _refresh_state_tick(self) -> None:
        try:
            self._render_state(self.runtime.get_state())
        finally:
            self.root.after(1200, self._refresh_state_tick)

    def _render_state(self, state: Dict[str, Any]) -> None:
        self.current_state = state
        self.hero_var.set(state["session"].get("status_message") or "等待配置")
        self.session_var.set("运行中" if state["session"].get("active") else "待机")
        self._update_session_badge()
        self._render_summary(state)
        self._render_checks(state.get("self_check", []))
        self._render_logs(state.get("logs", []))
        self._render_streams(state.get("streams", []))

    def _update_session_badge(self) -> None:
        if self.session_badge is None:
            return
        active = bool(self.current_state.get("session", {}).get("active"))
        self.session_badge.configure(bg="#20c997" if active else "#f6c344")

    def _render_summary(self, state: Dict[str, Any]) -> None:
        summary = state.get("summary", {})
        session = state.get("session", {})
        self.summary_vars["mode"].set(session.get("mode") or "-")
        self.summary_vars["online"].set(str(summary.get("online_nodes", 0)))
        self.summary_vars["offline"].set(str(summary.get("offline_nodes", 0)))
        self.summary_vars["voice"].set("ON" if summary.get("voice_running") else "OFF")

        available_width = max(self.summary_frame.winfo_width(), self.left_panel_width - 48)
        desired_columns = 1 if available_width < 420 else 2
        if desired_columns != self.summary_columns or not self.summary_frame.winfo_children():
            self.summary_columns = desired_columns
            for child in list(self.summary_frame.winfo_children()):
                child.destroy()
            for column in range(4):
                self.summary_frame.columnconfigure(column, weight=0, uniform="")
            cards = [
                ("模式", self.summary_vars["mode"]),
                ("在线节点", self.summary_vars["online"]),
                ("离线节点", self.summary_vars["offline"]),
                ("语音助手", self.summary_vars["voice"]),
            ]
            for column in range(self.summary_columns):
                self.summary_frame.columnconfigure(column, weight=1, uniform="summary")
            for idx, (label, variable) in enumerate(cards):
                card = ttk.Frame(self.summary_frame, style="Card.TFrame", padding=12)
                row = idx // self.summary_columns
                column = idx % self.summary_columns
                card.grid(row=row, column=column, sticky="nsew", padx=6, pady=6)
                ttk.Label(card, text=label, style="MetricLabel.TLabel").pack(anchor="w")
                ttk.Label(card, textvariable=variable, style="MetricValue.TLabel").pack(anchor="w", pady=(8, 0))

    def _render_checks(self, checks: List[Dict[str, Any]]) -> None:
        self.check_tree.delete(*self.check_tree.get_children())
        for item in checks:
            self.check_tree.insert("", "end", values=(item.get("status", "-"), item.get("summary", "")))

    def _render_logs(self, logs: List[Dict[str, Any]]) -> None:
        recent = logs[-120:]
        lines = []
        for row in recent:
            rendered = row.get("rendered")
            if rendered is not None:
                lines.append(str(rendered))
            else:
                lines.append(f"[{row['timestamp']}] [{row['level']}] {row['text']}")
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", tk.END)
        self.log_text.insert("1.0", "\n".join(lines))
        self.log_text.see(tk.END)
        self.log_text.configure(state="disabled")

    def _effective_left_width(self) -> int:
        return 0 if self.left_collapsed_var.get() else self.left_panel_width

    def _compute_stream_layout(self, stream_count: int) -> tuple[int, int, int]:
        available_width = max(self.wall_canvas.winfo_width() - 32, self.window_width - self._effective_left_width() - 160)
        if stream_count <= 1:
            columns = 1
        elif stream_count >= 3 and available_width >= 1650:
            columns = 3
        elif available_width >= 860:
            columns = 2
        else:
            columns = 1
        preview_width = int((available_width - (columns - 1) * 16 - 24) / columns)
        preview_width = max(320, min(560, preview_width))
        preview_height = max(180, int(preview_width * 9 / 16))
        return columns, preview_width, preview_height

    def _compute_text_limit(self, width: int, density: float, minimum: int, maximum: int) -> int:
        estimate = int(width / density)
        return max(minimum, min(maximum, estimate))

    def _truncate_text(self, text: str, limit: int) -> str:
        if len(text) <= limit:
            return text
        return text[: max(1, limit - 3)].rstrip() + "..."

    def _apply_stream_text(self, card: Dict[str, Any], stream: Dict[str, Any]) -> None:
        title_text = f"{stream['title']} | {stream['address']}"
        hint_text = stream.get("hint") or "等待状态更新"
        meta_text = f"{stream['subtitle']} | Mic {'Yes' if stream['caps'].get('has_mic') else 'No'} | Speaker {'Yes' if stream['caps'].get('has_speaker') else 'No'}"
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
            self.stream_frame_cache[stream["id"]] = frame.copy()
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
        ttk.Label(header, textvariable=self.stream_viewer_meta_var, style="Body.TLabel").grid(row=1, column=0, sticky="w", pady=(8, 0))

        body = ttk.Frame(shell, style="Panel.TFrame", padding=16)
        body.grid(row=1, column=0, sticky="nsew", pady=(16, 0))
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)
        self.stream_viewer_label = tk.Label(body, bg="#101820")
        self.stream_viewer_label.grid(row=0, column=0, sticky="nsew")

        footer = ttk.Frame(shell, style="Panel.TFrame", padding=(10, 12))
        footer.grid(row=2, column=0, sticky="ew", pady=(16, 0))
        footer.columnconfigure(0, weight=1)
        ttk.Label(footer, text="点击右侧监控卡片可切换查看对象，画面将随实时流同步刷新。", style="Foot.TLabel").grid(row=0, column=0, sticky="w")
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
        self.root.after(150, self._show_copyright_window)

    def _show_about_window(self) -> None:
        window = tk.Toplevel(self.root)
        window.title(f"关于 {APP_DISPLAY_NAME}")
        self._set_window_geometry(window, 820, 560, 680, 480)
        window.configure(bg="#0f1720")
        window.transient(self.root)
        self._apply_window_icon(window)
        self.window_refs.append(window)

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
        ttk.Label(shell, text=f"版本 v{self.runtime.version} | {COMPANY_NAME}", style="Body.TLabel").grid(row=2, column=1, sticky="w", pady=(12, 0))
        ttk.Label(shell, text=APP_DESCRIPTION, style="Body.TLabel", wraplength=520).grid(row=3, column=1, sticky="w", pady=(12, 0))

        body = ttk.Frame(shell, style="Panel.TFrame", padding=18)
        body.grid(row=4, column=0, columnspan=2, sticky="nsew", pady=(20, 0))
        body.columnconfigure(0, weight=1)
        ttk.Label(body, text="核心能力", style="PanelTitle.TLabel").grid(row=0, column=0, sticky="w")
        feature_text = (
            "1. 桌面式运行配置与启动自检\n"
            "2. 本机与多节点平铺监控墙\n"
            "3. 节点提示信息与运行日志统一展示\n"
            "4. 软件图标、版本资源、版权信息统一内置\n"
            "5. 适合软件著作权截图、演示与交付"
        )
        ttk.Label(body, text=feature_text, style="Body.TLabel", justify="left").grid(row=1, column=0, sticky="w", pady=(12, 0))
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
        set_config("desktop_ui.left_collapsed", self.left_collapsed_var.get())
        set_config("desktop_ui.demo_mode", self.demo_mode_var.get())

    def _restore_window_state(self) -> None:
        geometry = str(get_config("desktop_ui.window_geometry", "") or "").strip()
        state = str(get_config("desktop_ui.window_state", "normal") or "normal").lower()
        collapsed = bool(get_config("desktop_ui.left_collapsed", False))
        demo_mode = bool(get_config("desktop_ui.demo_mode", False))
        if geometry:
            try:
                safe_geometry = self._sanitize_geometry(geometry)
                if safe_geometry is not None:
                    self.root.geometry(safe_geometry)
            except Exception:
                pass
        self.root.update_idletasks()
        if collapsed:
            self._set_left_panel_collapsed(True, persist=False)
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
        self._set_left_panel_collapsed(False, persist=False)
        if self.demo_mode_var.get():
            self._toggle_demo_mode(False, persist=False)
        self._sync_monitor_metrics()
        self._configure_window_metrics()
        self._schedule_responsive_refresh()
        self._schedule_window_state_save()

    def _set_left_panel_collapsed(self, collapsed: bool, persist: bool = True) -> None:
        self.left_collapsed_var.set(bool(collapsed))
        if self.left_panel is None or self.shell_frame is None:
            return
        if collapsed:
            self.left_panel.grid_remove()
            self.shell_frame.columnconfigure(0, minsize=0)
        else:
            self.left_panel.grid()
            self.shell_frame.columnconfigure(0, minsize=self.left_panel_width)
        self._schedule_responsive_refresh()
        if persist:
            self._schedule_window_state_save()

    def _toggle_left_panel(self) -> None:
        self._set_left_panel_collapsed(not self.left_collapsed_var.get())

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
            self.demo_restore_collapsed = self.left_collapsed_var.get()
            self.demo_mode_var.set(True)
            self._set_left_panel_collapsed(True, persist=False)
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
            self._set_left_panel_collapsed(self.demo_restore_collapsed, persist=False)
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
        if not self.left_collapsed_var.get():
            new_left_width = self._compute_left_panel_width(current_width)
            if self.left_panel is not None and abs(new_left_width - self.left_panel_width) >= 8:
                self.left_panel_width = new_left_width
                self.left_panel.configure(width=self.left_panel_width)
                if self.shell_frame is not None:
                    self.shell_frame.columnconfigure(0, minsize=self.left_panel_width)
        effective_left = self._effective_left_width()
        self.hero_wraplength = max(480, min(current_width - effective_left - 280, 1120))
        self.info_wraplength = max(260, self.left_panel_width - 72)
        if self.hero_message_label is not None:
            self.hero_message_label.configure(wraplength=self.hero_wraplength)
        if self.info_description_label is not None:
            self.info_description_label.configure(wraplength=self.info_wraplength)
        if self.info_copyright_label is not None:
            self.info_copyright_label.configure(wraplength=self.info_wraplength)
        if self.check_tree is not None and self.left_canvas is not None:
            status_width = max(78, min(96, int(max(self.left_canvas.winfo_width(), 320) * 0.2)))
            summary_width = max(220, max(self.left_canvas.winfo_width(), 320) - status_width - 48)
            self.check_tree.column("status", width=status_width)
            self.check_tree.column("summary", width=summary_width)
        self._render_summary(self.current_state)
        layout_changed = self._relayout_stream_cards(self.current_state.get("streams", []))
        if layout_changed:
            self._refresh_cached_stream_images()

    def _on_left_inner_configure(self, _event: tk.Event) -> None:
        if self.left_canvas is not None:
            self.left_canvas.configure(scrollregion=self.left_canvas.bbox("all"))

    def _on_left_canvas_configure(self, event: tk.Event) -> None:
        if self.left_canvas is not None and self.left_window is not None:
            self.left_canvas.itemconfigure(self.left_window, width=event.width)
        self._schedule_responsive_refresh()

    def _on_wall_configure(self, _event: tk.Event) -> None:
        self.wall_canvas.configure(scrollregion=self.wall_canvas.bbox("all"))

    def _on_canvas_configure(self, event: tk.Event) -> None:
        self.wall_canvas.itemconfigure(self.wall_window, width=event.width)
        self._schedule_responsive_refresh()

    def _on_root_configure(self, event: tk.Event) -> None:
        if event.widget is not self.root:
            return
        scale_changed = self._sync_monitor_metrics()
        if scale_changed:
            self._schedule_responsive_refresh()
        self._schedule_responsive_refresh()
        self._schedule_window_state_save()

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
        software_menu.add_command(label="运行启动自检", command=self._run_self_check)
        software_menu.add_command(label="刷新模型清单", command=self._refresh_models)
        software_menu.add_command(label="专家模型管理", command=self._show_expert_window)
        software_menu.add_command(label="知识库管理", command=self._show_knowledge_base_window)
        software_menu.add_command(label="云模型配置", command=self._show_cloud_backend_window)
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
        view_menu.add_command(label="折叠 / 展开左栏", command=self._toggle_left_panel)
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
        payload = self.runtime.bootstrap()
        controls = payload["controls"]
        self.backend_combo["values"] = [item["label"] for item in controls["backends"]]
        self.backend_map = {item["label"]: item["value"] for item in controls["backends"]}
        self.backend_reverse = {value: label for label, value in self.backend_map.items()}
        self.mode_combo["values"] = [item["label"] for item in controls["modes"]]
        self.mode_map = {item["label"]: item["value"] for item in controls["modes"]}
        self.mode_reverse = {value: label for label, value in self.mode_map.items()}
        self.model_catalog = controls["models"]
        self.knowledge_catalog = payload.get("knowledge_bases", [])
        self.expert_catalog = payload.get("experts", [])
        self.cloud_backend_catalog = payload.get("cloud_backends", [])
        self._sync_knowledge_scope_choices()

        self.backend_var.set(controls["defaults"]["ai_backend"])
        self.mode_var.set(controls["defaults"]["mode"])
        self.backend_combo.set(self.backend_reverse.get(self.backend_var.get(), self.backend_combo.get()))
        self.mode_combo.set(self.mode_reverse.get(self.mode_var.get(), self.mode_combo.get()))
        self.expected_nodes_var.set(str(controls["defaults"]["expected_nodes"]))
        self.expected_entry.delete(0, tk.END)
        self.expected_entry.insert(0, self.expected_nodes_var.get())

        self._update_model_choices(controls["defaults"]["selected_model"])
        self.current_state = payload["state"]
        self._render_summary(payload["state"])
        self._render_checks(payload["state"]["self_check"])
        self._render_logs(payload["state"]["logs"])
        self._render_streams(payload["state"]["streams"])
        self.splash_message_var.set("基础环境加载完成，正在进入主界面…")
        self.root.after(450, self._finish_startup)

    def _refresh_models(self) -> None:
        self.hero_var.set("正在刷新模型与后端配置")
        self._dispatch("refresh_models", self.runtime.refresh_model_catalog)
        self._dispatch("cloud_catalog", self.runtime.get_cloud_backend_catalog)

    def _refresh_knowledge_bases(self) -> None:
        self.hero_var.set("正在刷新知识库目录")
        self._dispatch("kb_catalog", self.runtime.get_knowledge_base_catalog)

    def _refresh_expert_catalog(self) -> None:
        self.hero_var.set("正在刷新专家模型目录")
        self._dispatch("expert_catalog", self.runtime.get_expert_catalog)

    def _refresh_cloud_backend_catalog(self) -> None:
        self.hero_var.set("正在刷新云模型配置")
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
        self.kb_status_var.set(f"正在导入 {len(paths)} 项知识资产到 {scope_name}")
        self.hero_var.set("正在导入知识资产")
        self._dispatch(
            "kb_import",
            lambda: self.runtime.import_knowledge_paths(
                list(paths),
                scope_name=scope_name,
                reset_index=bool(self.kb_reset_var.get()),
                structured=bool(self.kb_structured_var.get()),
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
        docs = row.get("docs") or []
        lines = [
            f"作用域: {row.get('scope', '')}",
            f"名称: {row.get('title', '')}",
            f"文档数量: {row.get('doc_count', 0)}",
            f"向量索引: {'已准备' if row.get('vector_ready') else '轻量模式 / 未启用'}",
            f"结构化知识库: {'已准备' if row.get('structured_ready') else '待导入'}",
            f"文档目录: {row.get('docs_dir', '')}",
            f"向量目录: {row.get('vector_path', '')}",
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
                    "已准备" if row.get("structured_ready") else "待导入",
                ),
            )
        if self.knowledge_catalog:
            first_scope = self.knowledge_catalog[0]["scope"]
            self.kb_tree.selection_set(first_scope)
            self._render_kb_detail(self.knowledge_catalog[0])
            if self.kb_scope_combo is not None:
                self.kb_scope_combo.set(self.kb_scope_reverse.get(first_scope, self.kb_scope_combo.get()))
        self.kb_status_var.set(f"已加载 {len(self.knowledge_catalog)} 个知识库作用域")

    def _show_knowledge_base_window(self) -> None:
        if self.kb_window is not None and self.kb_window.winfo_exists():
            self.kb_window.deiconify()
            self.kb_window.lift()
            self.kb_window.focus_force()
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
        ttk.Label(
            header,
            text="支持公共背景知识库与专家专属知识库；文本、语音、视频、图片都可一键导入。",
            style="Body.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(8, 0))

        control = ttk.Frame(shell, style="Panel.TFrame", padding=16)
        control.grid(row=1, column=0, sticky="nsew", pady=(16, 0))
        control.columnconfigure(0, weight=3)
        control.columnconfigure(1, weight=2)
        control.rowconfigure(1, weight=1)

        topbar = ttk.Frame(control, style="SoftPanel.TFrame", padding=12)
        topbar.grid(row=0, column=0, columnspan=2, sticky="ew")
        topbar.columnconfigure(1, weight=1)
        ttk.Label(topbar, text="导入目标", style="Body.TLabel").grid(row=0, column=0, sticky="w")
        self.kb_scope_combo = ttk.Combobox(topbar, state="readonly")
        self.kb_scope_combo.grid(row=0, column=1, sticky="ew", padx=(10, 12))
        ttk.Checkbutton(topbar, text="导入前重建当前作用域索引", variable=self.kb_reset_var).grid(row=0, column=2, sticky="w", padx=(0, 10))
        ttk.Checkbutton(topbar, text="同步写入结构化知识库", variable=self.kb_structured_var).grid(row=0, column=3, sticky="w", padx=(0, 10))
        ttk.Button(topbar, text="导入文本 / 表格", command=self._import_knowledge_files).grid(row=0, column=4, sticky="ew", padx=(0, 8))
        ttk.Button(topbar, text="导入语音 / 视频 / 图片", command=self._import_knowledge_media_files).grid(row=0, column=5, sticky="ew", padx=(0, 8))
        ttk.Button(topbar, text="导入整个目录", command=self._import_knowledge_folder).grid(row=0, column=6, sticky="ew", padx=(0, 8))
        ttk.Button(topbar, text="导入公共背景库", command=lambda: self._import_knowledge_files("common")).grid(row=0, column=7, sticky="ew", padx=(0, 8))
        ttk.Button(topbar, text="刷新目录", command=self._refresh_knowledge_bases).grid(row=0, column=8, sticky="ew")

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
        ttk.Label(footer, textvariable=self.kb_status_var, style="Foot.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Button(footer, text="关闭", command=_close_window).grid(row=0, column=1, sticky="e")

        self._sync_knowledge_scope_choices()
        if self.kb_scope_combo["values"]:
            self.kb_scope_combo.set(self.kb_scope_combo["values"][0])
        self._populate_knowledge_tree()
        self._refresh_knowledge_bases()

    def _render_expert_detail(self, row: Dict[str, Any]) -> None:
        if self.expert_detail_text is None:
            return
        lines = [
            f"专家名称: {row.get('display_name', '')}",
            f"专家编码: {row.get('expert_code', '')}",
            f"专家类别: {row.get('category', '')}",
            f"说明: {row.get('description', '')}",
            f"已加载到系统: {'是' if row.get('loaded') else '否'}",
            f"需要专家模型: {'是' if row.get('model_required') else '否'}",
            f"需要知识库: {'是' if row.get('knowledge_required') else '否'}",
            f"专家模型目录: {row.get('asset_path', '')}",
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
                    "已准备" if row.get("knowledge_ready") else "待导入",
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
            messagebox.showwarning(APP_DISPLAY_NAME, "请先选择一个专家。", parent=self.expert_window or self.root)
            return
        if choose_folder:
            directory = filedialog.askdirectory(parent=self.expert_window or self.root, title="选择专家模型目录")
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
            messagebox.showwarning(APP_DISPLAY_NAME, "请先选择一个专家。", parent=self.expert_window or self.root)
            return
        self._import_knowledge_files(row["knowledge_scope"])

    def _import_selected_expert_knowledge_media(self) -> None:
        row = self._selected_expert_row()
        if row is None:
            messagebox.showwarning(APP_DISPLAY_NAME, "请先选择一个专家。", parent=self.expert_window or self.root)
            return
        self._import_knowledge_media_files(row["knowledge_scope"])

    def _show_expert_window(self) -> None:
        if self.expert_window is not None and self.expert_window.winfo_exists():
            self.expert_window.deiconify()
            self.expert_window.lift()
            self.expert_window.focus_force()
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
        ttk.Label(
            header,
            text="默认发布版不内置大体积专家模型。请按需导入模型资产；需要知识库的专家，再导入对应知识文件。",
            style="Body.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(8, 0))

        body = ttk.Frame(shell, style="Panel.TFrame", padding=16)
        body.grid(row=1, column=0, sticky="nsew", pady=(16, 0))
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(1, weight=1)

        topbar = ttk.Frame(body, style="SoftPanel.TFrame", padding=12)
        topbar.grid(row=0, column=0, columnspan=2, sticky="ew")
        ttk.Button(topbar, text="导入模型文件", command=lambda: self._import_selected_expert_assets(False)).grid(row=0, column=0, sticky="ew", padx=(0, 8))
        ttk.Button(topbar, text="导入模型目录", command=lambda: self._import_selected_expert_assets(True)).grid(row=0, column=1, sticky="ew", padx=(0, 8))
        ttk.Button(topbar, text="导入该专家知识文本", command=self._import_selected_expert_knowledge_text).grid(row=0, column=2, sticky="ew", padx=(0, 8))
        ttk.Button(topbar, text="导入该专家媒体知识", command=self._import_selected_expert_knowledge_media).grid(row=0, column=3, sticky="ew", padx=(0, 8))
        ttk.Button(topbar, text="刷新目录", command=self._refresh_expert_catalog).grid(row=0, column=4, sticky="ew")

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
        ttk.Label(footer, textvariable=self.expert_status_var, style="Foot.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Button(footer, text="关闭", command=_close_window).grid(row=0, column=1, sticky="e")

        self._populate_expert_tree()
        self._refresh_expert_catalog()

    def _selected_cloud_backend(self) -> str:
        if self.cloud_provider_combo is None:
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
            self.cloud_provider_combo["values"] = labels
            if labels and not self.cloud_provider_combo.get():
                self.cloud_provider_combo.set(labels[0])

    def _load_selected_cloud_backend_into_form(self) -> None:
        backend = self._selected_cloud_backend()
        for row in self.cloud_backend_catalog:
            if row["backend"] != backend:
                continue
            if self.cloud_api_key_entry is not None:
                self.cloud_api_key_entry.delete(0, tk.END)
                self.cloud_api_key_entry.insert(0, str(row.get("api_key", "")))
            if self.cloud_base_url_entry is not None:
                self.cloud_base_url_entry.delete(0, tk.END)
                self.cloud_base_url_entry.insert(0, str(row.get("base_url", "")))
            if self.cloud_model_entry is not None:
                self.cloud_model_entry.delete(0, tk.END)
                self.cloud_model_entry.insert(0, str(row.get("model", "")))
            configured = "已配置" if row.get("configured") else "待配置"
            self.cloud_status_var.set(f"{row.get('label', backend)} 当前状态：{configured}")
            break

    def _save_cloud_backend_from_form(self) -> None:
        backend = self._selected_cloud_backend()
        api_key = self.cloud_api_key_entry.get().strip() if self.cloud_api_key_entry is not None else ""
        base_url = self.cloud_base_url_entry.get().strip() if self.cloud_base_url_entry is not None else ""
        model = self.cloud_model_entry.get().strip() if self.cloud_model_entry is not None else ""
        self.cloud_status_var.set("正在保存云模型配置")
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
        if self.cloud_window is not None and self.cloud_window.winfo_exists():
            self.cloud_window.deiconify()
            self.cloud_window.lift()
            self.cloud_window.focus_force()
            self._refresh_cloud_backend_catalog()
            return

        window = tk.Toplevel(self.root)
        window.title(f"{APP_DISPLAY_NAME} - 云模型配置")
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
        ttk.Label(header, text="云模型配置", style="Header.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            header,
            text="支持通义千问、OpenAI、DeepSeek、Kimi 及兼容 OpenAI 协议的云大模型；使用前请填写 API Key。",
            style="Body.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(8, 0))

        body = ttk.Frame(shell, style="Panel.TFrame", padding=16)
        body.grid(row=1, column=0, sticky="nsew", pady=(16, 0))
        body.columnconfigure(0, weight=1)

        ttk.Label(body, text="服务商", style="Body.TLabel").grid(row=0, column=0, sticky="w")
        self.cloud_provider_combo = ttk.Combobox(body, state="readonly")
        self.cloud_provider_combo.grid(row=1, column=0, sticky="ew", pady=(6, 10))
        self.cloud_provider_combo.bind("<<ComboboxSelected>>", lambda _event: self._load_selected_cloud_backend_into_form())
        self.cloud_api_key_entry = self._add_labeled_entry(body, 2, "API Key")
        self.cloud_base_url_entry = self._add_labeled_entry(body, 3, "Base URL")
        self.cloud_model_entry = self._add_labeled_entry(body, 4, "默认模型")

        actions = ttk.Frame(body, style="SoftPanel.TFrame")
        actions.grid(row=5, column=0, sticky="ew", pady=(8, 0))
        actions.columnconfigure(0, weight=1)
        actions.columnconfigure(1, weight=1)
        actions.columnconfigure(2, weight=1)
        ttk.Button(actions, text="保存配置", command=self._save_cloud_backend_from_form).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ttk.Button(actions, text="刷新列表", command=self._refresh_cloud_backend_catalog).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(actions, text="关闭", command=_close_window).grid(row=0, column=2, sticky="ew", padx=(6, 0))

        footer = ttk.Frame(shell, style="Panel.TFrame", padding=(10, 12))
        footer.grid(row=2, column=0, sticky="ew", pady=(16, 0))
        footer.columnconfigure(0, weight=1)
        ttk.Label(footer, textvariable=self.cloud_status_var, style="Foot.TLabel").grid(row=0, column=0, sticky="w")

        self._sync_cloud_provider_choices()
        self._refresh_cloud_backend_catalog()

    def _process_queue(self) -> None:
        try:
            while True:
                status, name, payload = self.ui_queue.get_nowait()
                if status == "error":
                    self.hero_var.set(f"{name} 失败: {payload}")
                    if self.splash is not None:
                        self.splash_message_var.set(f"初始化失败：{payload}")
                    messagebox.showerror(APP_DISPLAY_NAME, str(payload), parent=self.root)
                    continue

                if name == "refresh_models":
                    self.model_catalog = payload
                    self._update_model_choices()
                    self.hero_var.set("模型清单已刷新")
                elif name == "kb_catalog":
                    self.knowledge_catalog = payload
                    self._sync_knowledge_scope_choices()
                    self._populate_knowledge_tree()
                    self.hero_var.set("知识库目录已刷新")
                elif name == "kb_import":
                    self.kb_status_var.set(
                        f"导入完成: 作用域={payload['scope']}，成功 {payload['imported_count']} 项，失败 {payload['failed_count']} 项"
                    )
                    self.hero_var.set("知识库导入已完成")
                    self._render_logs(self.runtime.get_state().get("logs", []))
                    self._refresh_knowledge_bases()
                    self._refresh_expert_catalog()
                    messagebox.showinfo(
                        APP_DISPLAY_NAME,
                        f"作用域: {payload['scope']}\n成功: {payload['imported_count']}\n失败: {payload['failed_count']}\n结构化记录: {payload.get('structured_records', 0)}",
                        parent=self.kb_window or self.expert_window or self.root,
                    )
                elif name == "expert_catalog":
                    self.expert_catalog = payload
                    self._populate_expert_tree()
                    self.hero_var.set("专家模型目录已刷新")
                elif name == "expert_import":
                    self.expert_status_var.set(
                        f"导入完成: {payload['display_name']}，成功 {payload['imported_count']} 项，失败 {payload['failed_count']} 项"
                    )
                    self.hero_var.set("专家模型导入已完成")
                    self._refresh_expert_catalog()
                    messagebox.showinfo(
                        APP_DISPLAY_NAME,
                        f"专家: {payload['display_name']}\n成功: {payload['imported_count']}\n失败: {payload['failed_count']}\n目录: {payload['target_path']}",
                        parent=self.expert_window or self.root,
                    )
                elif name == "cloud_catalog":
                    rows = list(payload)
                    for row in rows:
                        row["configured"] = bool(row.get("api_key"))
                    self.cloud_backend_catalog = rows
                    self._sync_cloud_provider_choices()
                    self._load_selected_cloud_backend_into_form()
                    self.hero_var.set("云模型配置已刷新")
                elif name == "cloud_save":
                    self.cloud_status_var.set(f"{payload['label']} 配置已保存")
                    self.hero_var.set("云模型配置已保存")
                    self._refresh_cloud_backend_catalog()
                    self._refresh_models()
                elif name == "self_check":
                    self._render_checks(payload)
                    self._render_logs(self.runtime.get_state().get("logs", []))
                    self.hero_var.set("启动自检已完成")
                elif name in {"start_session", "stop_session"}:
                    self._render_state(payload)
        except queue.Empty:
            pass
        self.root.after(250, self._process_queue)

    def _on_close(self) -> None:
        try:
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
            self.runtime.shutdown()
        finally:
            self._hide_tooltip()
            self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def launch_desktop_app() -> int:
    app = DesktopApp()
    app.run()
    return 0
