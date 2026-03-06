#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Desktop visualization app for LabDetector."""

from __future__ import annotations

import queue
import re
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, Dict, List

import cv2
from PIL import Image, ImageTk

from pcside.app_identity import (
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
from pcside.webui.runtime import LabDetectorRuntime


class DesktopApp:
    def __init__(self) -> None:
        self.runtime = LabDetectorRuntime()
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title(f"{APP_DISPLAY_NAME} v{self.runtime.version}")
        self.root.geometry("1600x1020")
        self.root.minsize(1280, 860)
        self.root.configure(bg="#0f1720")

        self.ui_queue: queue.Queue[tuple[str, str, Any]] = queue.Queue()
        self.photo_refs: Dict[str, ImageTk.PhotoImage] = {}
        self.stream_cards: Dict[str, Dict[str, Any]] = {}
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

        self.summary_vars = {
            "mode": tk.StringVar(value="-"),
            "online": tk.StringVar(value="0"),
            "offline": tk.StringVar(value="0"),
            "voice": tk.StringVar(value="OFF"),
        }

        self._build_style()
        self._apply_branding()
        self._build_menu()
        self._build_layout()
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
        style.configure("TButton", font=("Microsoft YaHei UI", 10), padding=(10, 8))
        style.configure("Accent.TButton", font=("Microsoft YaHei UI", 10, "bold"))
        style.configure("TCombobox", padding=6)
        style.configure("Treeview", rowheight=30, font=("Microsoft YaHei UI", 10), fieldbackground="#223143", background="#223143", foreground="#f5f7fb")
        style.configure("Treeview.Heading", font=("Microsoft YaHei UI", 10, "bold"))

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

        help_menu = tk.Menu(menubar, tearoff=False, bg="#182330", fg="#f5f7fb", activebackground="#20c997", activeforeground="#0f1720")
        help_menu.add_command(label="软件说明", command=self._show_manual_window)
        help_menu.add_command(label="关于软件", command=self._show_about_window)
        help_menu.add_command(label="版权信息", command=self._show_copyright_window)

        menubar.add_cascade(label="软件", menu=software_menu)
        menubar.add_cascade(label="帮助", menu=help_menu)
        self.root.configure(menu=menubar)
    def _build_layout(self) -> None:
        shell = ttk.Frame(self.root, style="Root.TFrame", padding=18)
        shell.pack(fill="both", expand=True)
        shell.columnconfigure(0, weight=0)
        shell.columnconfigure(1, weight=1)
        shell.rowconfigure(1, weight=1)
        shell.rowconfigure(2, weight=1)

        hero = ttk.Frame(shell, style="Panel.TFrame", padding=20)
        hero.grid(row=0, column=0, columnspan=2, sticky="nsew", pady=(0, 16))
        hero.columnconfigure(0, weight=1)
        hero.columnconfigure(1, weight=0)

        hero_left = ttk.Frame(hero, style="Panel.TFrame")
        hero_left.grid(row=0, column=0, sticky="w")
        ttk.Label(hero_left, text=APP_DISPLAY_NAME, style="Header.TLabel").pack(anchor="w")
        ttk.Label(hero_left, text=APP_SHORT_TAGLINE, style="Brand.TLabel").pack(anchor="w", pady=(6, 0))
        ttk.Label(hero_left, textvariable=self.hero_var, style="Body.TLabel", wraplength=860).pack(anchor="w", pady=(8, 0))
        ttk.Label(hero_left, textvariable=self.brand_var, style="Foot.TLabel").pack(anchor="w", pady=(10, 0))

        hero_right = ttk.Frame(hero, style="Panel.TFrame")
        hero_right.grid(row=0, column=1, sticky="e")
        self.session_badge = tk.Label(hero_right, textvariable=self.session_var, bg="#1fb68d", fg="#0f1720", font=("Microsoft YaHei UI", 11, "bold"), padx=14, pady=8)
        self.session_badge.pack(anchor="e")
        ttk.Button(hero_right, text="运行启动自检", command=self._run_self_check).pack(anchor="e", pady=(10, 0), fill="x")
        ttk.Button(hero_right, text="知识库管理", command=self._show_knowledge_base_window).pack(anchor="e", pady=(8, 0), fill="x")
        ttk.Button(hero_right, text="软件说明", command=self._show_manual_window).pack(anchor="e", pady=(8, 0), fill="x")
        ttk.Button(hero_right, text="关于 / 版权", command=self._show_about_and_copyright).pack(anchor="e", pady=(8, 0), fill="x")

        left = ttk.Frame(shell, style="Panel.TFrame", padding=18)
        left.grid(row=1, column=0, rowspan=2, sticky="nsew", padx=(0, 16))
        left.configure(width=400)
        left.grid_propagate(False)
        left.columnconfigure(0, weight=1)
        left.rowconfigure(3, weight=1)
        left.rowconfigure(5, weight=1)

        config_panel = ttk.Frame(left, style="SoftPanel.TFrame", padding=16)
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

        summary_panel = ttk.Frame(left, style="SoftPanel.TFrame", padding=16)
        summary_panel.grid(row=1, column=0, sticky="ew", pady=(16, 0))
        ttk.Label(summary_panel, text="运行概览", style="PanelTitle.TLabel").pack(anchor="w")
        self.summary_frame = ttk.Frame(summary_panel, style="SoftPanel.TFrame")
        self.summary_frame.pack(fill="x", pady=(12, 0))

        checks_panel = ttk.Frame(left, style="SoftPanel.TFrame", padding=16)
        checks_panel.grid(row=3, column=0, sticky="nsew", pady=(16, 0))
        checks_panel.columnconfigure(0, weight=1)
        checks_panel.rowconfigure(1, weight=1)
        ttk.Label(checks_panel, text="启动自检结果", style="PanelTitle.TLabel").grid(row=0, column=0, sticky="w")

        self.check_tree = ttk.Treeview(checks_panel, columns=("status", "summary"), show="headings", height=7)
        self.check_tree.heading("status", text="状态")
        self.check_tree.heading("summary", text="摘要")
        self.check_tree.column("status", width=80, anchor="center")
        self.check_tree.column("summary", width=260, anchor="w")
        self.check_tree.grid(row=1, column=0, sticky="nsew", pady=(12, 0))

        info_panel = ttk.Frame(left, style="SoftPanel.TFrame", padding=16)
        info_panel.grid(row=5, column=0, sticky="ew", pady=(16, 0))
        ttk.Label(info_panel, text="软件信息", style="PanelTitle.TLabel").pack(anchor="w")
        ttk.Label(info_panel, text=APP_DESCRIPTION, style="Body.TLabel", wraplength=320).pack(anchor="w", pady=(10, 0))
        ttk.Label(info_panel, text=COPYRIGHT_TEXT, style="Foot.TLabel", wraplength=320).pack(anchor="w", pady=(10, 0))

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

    def _show_startup_splash(self) -> None:
        splash = tk.Toplevel(self.root)
        splash.overrideredirect(True)
        splash.configure(bg="#071018")
        splash.attributes("-topmost", True)
        self.splash = splash

        width = 760
        height = 420
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
        ttk.Label(text_holder, textvariable=self.splash_message_var, style="SplashBody.TLabel", wraplength=420).pack(anchor="w", pady=(18, 0))
        ttk.Label(text_holder, text=COPYRIGHT_TEXT, style="Foot.TLabel", wraplength=420).pack(anchor="w", pady=(18, 0))

        progress = ttk.Progressbar(text_holder, mode="indeterminate", length=360)
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
        window.geometry("1080x720")
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
        self.hero_var.set(state["session"].get("status_message") or "等待配置")
        self.session_var.set("运行中" if state["session"].get("active") else "待机")
        self.session_badge.configure(bg="#20c997" if state["session"].get("active") else "#f6c344")
        self._render_summary(state)
        self._render_checks(state.get("self_check", []))
        self._render_logs(state.get("logs", []))
        self._render_streams(state.get("streams", []))

    def _render_summary(self, state: Dict[str, Any]) -> None:
        summary = state.get("summary", {})
        session = state.get("session", {})
        self.summary_vars["mode"].set(session.get("mode") or "-")
        self.summary_vars["online"].set(str(summary.get("online_nodes", 0)))
        self.summary_vars["offline"].set(str(summary.get("offline_nodes", 0)))
        self.summary_vars["voice"].set("ON" if summary.get("voice_running") else "OFF")

        if not self.summary_frame.winfo_children():
            cards = [
                ("模式", self.summary_vars["mode"]),
                ("在线节点", self.summary_vars["online"]),
                ("离线节点", self.summary_vars["offline"]),
                ("语音助手", self.summary_vars["voice"]),
            ]
            for idx, (label, variable) in enumerate(cards):
                card = ttk.Frame(self.summary_frame, style="Card.TFrame", padding=12)
                card.grid(row=idx // 2, column=idx % 2, sticky="nsew", padx=6, pady=6)
                self.summary_frame.columnconfigure(idx % 2, weight=1)
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

    def _render_streams(self, streams: List[Dict[str, Any]]) -> None:
        if not streams:
            for child in list(self.wall_inner.winfo_children()):
                child.destroy()
            self.stream_cards.clear()
            placeholder = ttk.Label(self.wall_inner, text="尚未启动监控。配置完成后点击“启动监控”。", style="Body.TLabel")
            placeholder.grid(row=0, column=0, padx=12, pady=18, sticky="w")
            return

        if len(streams) and any(not isinstance(child, ttk.Frame) for child in self.wall_inner.winfo_children()):
            for child in list(self.wall_inner.winfo_children()):
                child.destroy()
            self.stream_cards.clear()

        existing_ids = set(self.stream_cards.keys())
        target_ids = {stream["id"] for stream in streams}
        for stale_id in existing_ids - target_ids:
            card = self.stream_cards.pop(stale_id)
            card["frame"].destroy()
            self.photo_refs.pop(stale_id, None)

        for idx, stream in enumerate(streams):
            card = self._ensure_stream_card(stream["id"], idx)
            self._update_stream_card(card, stream)

    def _ensure_stream_card(self, stream_id: str, idx: int) -> Dict[str, Any]:
        if stream_id in self.stream_cards:
            frame = self.stream_cards[stream_id]["frame"]
            frame.grid(row=idx // 2, column=idx % 2, sticky="nsew", padx=8, pady=8)
            return self.stream_cards[stream_id]

        frame = ttk.Frame(self.wall_inner, style="Card.TFrame", padding=12)
        frame.grid(row=idx // 2, column=idx % 2, sticky="nsew", padx=8, pady=8)
        self.wall_inner.columnconfigure(idx % 2, weight=1)

        title_var = tk.StringVar(value=stream_id)
        status_var = tk.StringVar(value="offline")
        hint_var = tk.StringVar(value="等待状态更新")
        meta_var = tk.StringVar(value="")

        ttk.Label(frame, textvariable=title_var, style="PanelTitle.TLabel").grid(row=0, column=0, sticky="w")
        status_label = tk.Label(frame, textvariable=status_var, bg="#f6c344", fg="#0f1720", font=("Microsoft YaHei UI", 9, "bold"), padx=10, pady=4)
        status_label.grid(row=0, column=1, sticky="e")

        image_label = tk.Label(frame, bg="#101820", width=480, height=270)
        image_label.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(10, 10))
        ttk.Label(frame, textvariable=hint_var, style="Body.TLabel", wraplength=520).grid(row=2, column=0, columnspan=2, sticky="w")
        ttk.Label(frame, textvariable=meta_var, style="Body.TLabel", wraplength=520).grid(row=3, column=0, columnspan=2, sticky="w", pady=(8, 0))

        card = {
            "frame": frame,
            "title": title_var,
            "status": status_var,
            "hint": hint_var,
            "meta": meta_var,
            "status_label": status_label,
            "image_label": image_label,
        }
        self.stream_cards[stream_id] = card
        return card

    def _update_stream_card(self, card: Dict[str, Any], stream: Dict[str, Any]) -> None:
        card["title"].set(f"{stream['title']} · {stream['address']}")
        card["status"].set(stream["status"].upper())
        card["hint"].set(stream.get("hint") or "等待状态更新")
        card["meta"].set(
            f"{stream['subtitle']} | Mic {'Yes' if stream['caps'].get('has_mic') else 'No'} | Speaker {'Yes' if stream['caps'].get('has_speaker') else 'No'}"
        )
        badge_color = {
            "online": "#20c997",
            "connecting": "#f6c344",
            "offline": "#f06a6a",
        }.get(stream["status"], "#8899aa")
        card["status_label"].configure(bg=badge_color)

        frame = self.runtime._compose_frame(stream["id"])
        frame = cv2.resize(frame, (480, 270))
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        image = Image.fromarray(rgb)
        photo = ImageTk.PhotoImage(image)
        card["image_label"].configure(image=photo)
        self.photo_refs[stream["id"]] = photo
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
        window.geometry("760x520")
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
        window.geometry(size)
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

    def _on_wall_configure(self, _event: tk.Event) -> None:
        self.wall_canvas.configure(scrollregion=self.wall_canvas.bbox("all"))

    def _on_canvas_configure(self, event: tk.Event) -> None:
        self.wall_canvas.itemconfigure(self.wall_window, width=event.width)

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
            self.runtime.shutdown()
        finally:
            self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def launch_desktop_app() -> int:
    app = DesktopApp()
    app.run()
    return 0
