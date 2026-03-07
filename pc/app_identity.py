#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared product identity metadata for desktop packaging and UI."""

from __future__ import annotations

import sys
from pathlib import Path

APP_NAME = "LabDetector"
APP_DISPLAY_NAME = "LabDetector \u667a\u80fd\u5b9e\u9a8c\u5ba4\u76d1\u63a7\u8f6f\u4ef6"
APP_SHORT_TAGLINE = "\u5b9e\u9a8c\u5ba4\u591a\u8282\u70b9\u76d1\u63a7\u4e0e\u4e13\u5bb6\u8054\u52a8\u5e73\u53f0"
APP_DESCRIPTION = "\u9762\u5411\u5b9e\u9a8c\u5ba4\u573a\u666f\u7684\u53ef\u89c6\u5316\u76d1\u63a7\u3001\u4e13\u5bb6\u7814\u5224\u4e0e\u77e5\u8bc6\u589e\u5f3a\u684c\u9762\u8f6f\u4ef6\u3002"
COMPANY_NAME = "LabDetector \u8f6f\u4ef6\u7814\u53d1\u7ec4"
COMPANY_NAME_EN = "LabDetector Software Team"
COPYRIGHT_TEXT = "Copyright (C) 2026 LabDetector \u8f6f\u4ef6\u7814\u53d1\u7ec4. All rights reserved."
COPYRIGHT_TEXT_EN = "Copyright (C) 2026 LabDetector Software Team. All rights reserved."
LEGAL_NOTICE = (
    "LabDetector \u667a\u80fd\u5b9e\u9a8c\u5ba4\u76d1\u63a7\u8f6f\u4ef6\n\n"
    "\u8457\u4f5c\u6743\u4eba\uff1aLabDetector \u8f6f\u4ef6\u7814\u53d1\u7ec4\n"
    "\u5b8c\u6210\u65e5\u671f\uff1a2026 \u5e74 3 \u6708\n"
    "\u672c\u8f6f\u4ef6\u7528\u4e8e\u5b9e\u9a8c\u5ba4\u591a\u8282\u70b9\u76d1\u63a7\u3001\u4e13\u5bb6\u8f85\u52a9\u5206\u6790\u4e0e\u77e5\u8bc6\u589e\u5f3a\u5c55\u793a\u3002\n\n"
    "\u672c\u8f6f\u4ef6\u7684\u7a0b\u5e8f\u4ee3\u7801\u3001\u754c\u9762\u8bbe\u8ba1\u3001\u56fe\u6807\u8d44\u6e90\u3001\u8bf4\u660e\u6587\u6863\u53ca\u76f8\u5173\u6587\u5b57\u8bf4\u660e\uff0c\n"
    "\u5747\u7531 LabDetector \u8f6f\u4ef6\u7814\u53d1\u7ec4\u5b8c\u6210\u5e76\u4eab\u6709\u76f8\u5e94\u8457\u4f5c\u6743\u3002\n\n"
    "\u7b2c\u4e09\u65b9\u7ec4\u4ef6\u8bf4\u660e\n"
    "\u672c\u8f6f\u4ef6\u5728\u6784\u5efa\u6216\u8fd0\u884c\u8fc7\u7a0b\u4e2d\u53ef\u80fd\u4f7f\u7528 Python\u3001Tk\u3001OpenCV\u3001Pillow\u3001PyInstaller \u7b49\u5f00\u6e90\u7ec4\u4ef6\u3002"
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
    return project_root()


def pi_bundle_root() -> Path:
    if is_frozen_runtime():
        candidate = runtime_root() / "pi"
        if candidate.exists():
            return candidate
    return project_root() / "pi"


def resource_path(relative_path: str) -> Path:
    return pc_bundle_root() / relative_path


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
