#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared product identity metadata for desktop packaging and UI."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _module_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _identity_candidates() -> list[Path]:
    module_root = _module_root()
    candidates = [
        module_root / "project_identity.json",
        module_root.parent / "project_identity.json",
    ]

    bundle_root = getattr(sys, "_MEIPASS", "")
    if bundle_root:
        bundle_path = Path(bundle_root)
        candidates.extend(
            [
                bundle_path / "project_identity.json",
                bundle_path / "pc" / "project_identity.json",
            ]
        )

    if getattr(sys, "frozen", False):
        exe_root = Path(sys.executable).resolve().parent
        candidates.extend(
            [
                exe_root / "APP" / "project_identity.json",
                exe_root / "project_identity.json",
                exe_root.parent / "project_identity.json",
            ]
        )

    unique_candidates: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        unique_candidates.append(candidate)
    return unique_candidates


def _load_identity() -> dict[str, str]:
    for candidate in _identity_candidates():
        if not candidate.exists():
            continue
        return json.loads(candidate.read_text(encoding="utf-8"))
    raise FileNotFoundError(
        "project_identity.json not found. Searched: "
        + ", ".join(str(path) for path in _identity_candidates())
    )


PROJECT_ROOT = _module_root()
IDENTITY = _load_identity()

APP_NAME = IDENTITY["app_name"]
APP_DISPLAY_NAME = IDENTITY["short_name"]
APP_FORMAL_NAME = IDENTITY["formal_name"]
APP_SOFTWARE_FULL_NAME = IDENTITY["software_full_name"]
APP_SHORT_TAGLINE = IDENTITY["short_tagline"]
APP_DESCRIPTION = IDENTITY["description"]
COMPANY_NAME = IDENTITY["company_name_cn"]
COMPANY_NAME_EN = IDENTITY["company_name_en"]
COPYRIGHT_TEXT = IDENTITY["copyright_cn"]
COPYRIGHT_TEXT_EN = IDENTITY["copyright_en"]
DESKTOP_EXE_NAME = IDENTITY["desktop_exe"]
LLM_EXE_NAME = IDENTITY["llm_exe"]
VISION_EXE_NAME = IDENTITY["vision_exe"]
RELEASE_PREFIX = IDENTITY["release_prefix"]
LEGAL_NOTICE = (
    f"{APP_FORMAL_NAME}\n\n"
    f"著作权人：{COMPANY_NAME}\n"
    "完成日期：2026 年 3 月\n"
    "本软件用于实验室多节点监控、专家辅助分析、语音交互、知识增强与模型训练。\n\n"
    "本软件的程序代码、界面设计、图标资源、说明文档及相关文字说明，\n"
    f"均由 {COMPANY_NAME} 完成并享有相应著作权。\n\n"
    "第三方组件说明\n"
    "本软件在构建或运行过程中可能使用 Python、Tk、OpenCV、Pillow、PyInstaller、Transformers、PEFT、Ultralytics 等开源组件。"
)


def project_root() -> Path:
    return PROJECT_ROOT


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
    primary = project_root() / "pi"
    if primary.exists():
        return primary
    sibling = project_root().parent / "pi"
    if sibling.exists():
        return sibling
    return primary


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
    return resource_path("assets/branding/neurolab_hub.ico")


def logo_path() -> Path:
    return resource_path("assets/branding/neurolab_hub_logo.png")


def manual_path() -> Path:
    return _existing_resource(IDENTITY["manual_doc"])


def copyright_path() -> Path:
    return _existing_resource(IDENTITY["copyright_doc"])
