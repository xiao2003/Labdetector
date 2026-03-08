#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared product identity metadata for desktop packaging and UI."""

from __future__ import annotations

import sys
from pathlib import Path

APP_NAME = "NeuroLabHub"
APP_DISPLAY_NAME = "NeuroLab Hub"
APP_SHORT_TAGLINE = "AI for Science 实验室多节点监控与智能交互平台"
APP_DESCRIPTION = "面向科研实验室的多节点监控、风险研判、语音交互、知识沉淀与训练部署一体化桌面平台。"
COMPANY_NAME = "NeuroLab Hub 软件研发组"
COMPANY_NAME_EN = "NeuroLab Hub Software Team"
COPYRIGHT_TEXT = "Copyright (C) 2026 NeuroLab Hub 软件研发组. All rights reserved."
COPYRIGHT_TEXT_EN = "Copyright (C) 2026 NeuroLab Hub Software Team. All rights reserved."
LEGAL_NOTICE = (
    "NeuroLab Hub\n\n"
    "著作权人：NeuroLab Hub 软件研发组\n"
    "完成日期：2026 年 3 月\n"
    "本软件用于实验室多节点监控、专家辅助分析、语音交互、知识增强与模型训练。\n\n"
    "本软件的程序代码、界面设计、图标资源、说明文档及相关文字说明，\n"
    "均由 NeuroLab Hub 软件研发组完成并享有相应著作权。\n\n"
    "第三方组件说明\n"
    "本软件在构建或运行过程中可能使用 Python、Tk、OpenCV、Pillow、PyInstaller、Transformers、PEFT、Ultralytics 等开源组件。"
)


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def is_frozen_runtime() -> bool:
    return bool(getattr(sys, "frozen", False) or getattr(sys, "_MEIPASS", ""))


def launcher_root() -> Path:
    if is_frozen_runtime():
        return Path(sys.executable).resolve().parent
    return project_root()


def external_app_root() -> Path:
    if is_frozen_runtime():
        return launcher_root() / "APP"
    candidate = project_root() / "pc" / "APP"
    return candidate if candidate.exists() else project_root()


def runtime_root() -> Path:
    bundle_root = getattr(sys, "_MEIPASS", "")
    if bundle_root:
        return Path(bundle_root)
    return project_root()


def pc_bundle_root() -> Path:
    if is_frozen_runtime():
        candidate = runtime_root() / "pc"
        if candidate.exists():
            return candidate
    return project_root() / "pc"


def pi_bundle_root() -> Path:
    if is_frozen_runtime():
        candidate = runtime_root() / "pi"
        if candidate.exists():
            return candidate
    return project_root() / "pi"


def resource_path(relative_path: str) -> Path:
    normalized = str(relative_path or "").replace("\\", "/").strip("/")
    if not normalized:
        return runtime_root() if is_frozen_runtime() else project_root()
    if not is_frozen_runtime():
        return project_root() / normalized
    if normalized == "pc":
        return pc_bundle_root()
    if normalized.startswith("pc/"):
        return pc_bundle_root() / normalized[3:]
    if normalized == "pi":
        return pi_bundle_root()
    if normalized.startswith("pi/"):
        return pi_bundle_root() / normalized[3:]
    direct = runtime_root() / normalized
    if direct.exists():
        return direct
    return pc_bundle_root() / normalized


def runtime_path(relative_path: str) -> Path:
    return runtime_root() / relative_path


def _existing_resource(*candidates: str) -> Path:
    for candidate in candidates:
        path = resource_path(candidate)
        if path.exists():
            return path
    return resource_path(candidates[0])


def icon_path() -> Path:
    return resource_path("assets/branding/labdetector.ico")


def logo_path() -> Path:
    return resource_path("assets/branding/labdetector_logo.png")


def manual_path() -> Path:
    return _existing_resource("docs/LabDetector_Manual.md")


def copyright_path() -> Path:
    return _existing_resource("docs/LabDetector_Copyright.md")
