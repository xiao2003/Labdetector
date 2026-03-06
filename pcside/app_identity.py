#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared product identity metadata for desktop packaging and UI."""

from __future__ import annotations

import sys
from pathlib import Path


APP_NAME = "LabDetector"
APP_DISPLAY_NAME = "LabDetector 智能实验室监控软件"
APP_SHORT_TAGLINE = "实验室多节点可视化监控与智能提示平台"
APP_DESCRIPTION = "面向实验室安全巡检、多节点监控、事件提示与专家辅助分析的桌面可视化软件。"
COMPANY_NAME = "LabDetector 软件研发组"
COMPANY_NAME_EN = "LabDetector Software Team"
COPYRIGHT_TEXT = "Copyright (C) 2026 LabDetector 软件研发组. All rights reserved."
COPYRIGHT_TEXT_EN = "Copyright (C) 2026 LabDetector Software Team. All rights reserved."
LEGAL_NOTICE = """\
LabDetector 智能实验室监控软件

著作权归属：LabDetector 软件研发组
完成日期：2026 年 3 月
软件用途：实验室多节点监控、风险提示、事件记录与可视化运行控制。

本软件界面、图形标识、文字说明和程序代码用于 LabDetector 软件著作权登记、测试和交付展示。
未经著作权人书面许可，不得对软件整体进行再分发、反向编译、商业转售或冒用主体信息。

第三方组件说明：
本软件运行时可能集成 Python、Tk、OpenCV、Pillow、PyInstaller 等开源组件，相关组件版权归其原始作者或组织所有。
"""


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def runtime_root() -> Path:
    bundle_root = getattr(sys, "_MEIPASS", "")
    if bundle_root:
        return Path(bundle_root)
    return project_root()


def resource_path(relative_path: str) -> Path:
    return runtime_root() / relative_path


def icon_path() -> Path:
    return resource_path("assets/branding/labdetector.ico")


def logo_path() -> Path:
    return resource_path("assets/branding/labdetector_logo.png")


def manual_path() -> Path:
    return resource_path("docs/LabDetector软件说明书.md")


def copyright_path() -> Path:
    return resource_path("docs/软件版权声明.md")
