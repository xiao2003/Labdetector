#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared product identity metadata for desktop packaging and UI."""

from __future__ import annotations

import sys
from pathlib import Path

APP_NAME = "LabDetector"
APP_DISPLAY_NAME = "LabDetector 智能实验室监控软件"
APP_SHORT_TAGLINE = "实验室多节点监控与专家联动平台"
APP_DESCRIPTION = "面向实验室场景的可视化监控、专家研判与知识增强桌面软件。"
COMPANY_NAME = "LabDetector 软件研发组"
COMPANY_NAME_EN = "LabDetector Software Team"
COPYRIGHT_TEXT = "Copyright (C) 2026 LabDetector 软件研发组. All rights reserved."
COPYRIGHT_TEXT_EN = "Copyright (C) 2026 LabDetector Software Team. All rights reserved."
LEGAL_NOTICE = (
    "LabDetector 智能实验室监控软件\n\n"
    "著作权人：LabDetector 软件研发组\n"
    "完成日期：2026 年 3 月\n"
    "本软件用于实验室多节点监控、专家辅助分析与知识增强展示。\n\n"
    "本软件的程序代码、界面设计、图标资源、说明文档及相关文字说明，\n"
    "均由 LabDetector 软件研发组完成并享有相应著作权。\n\n"
    "第三方组件说明\n"
    "本软件在构建或运行过程中可能使用 Python、Tk、OpenCV、Pillow、PyInstaller 等开源组件。"
)


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def is_frozen_runtime() -> bool:
    return bool(getattr(sys, "frozen", False) or getattr(sys, "_MEIPASS", ""))


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
