#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Global app version reader."""

from __future__ import annotations

from pc.app_identity import pc_bundle_root, runtime_root


def get_app_version() -> str:
    search_paths = [
        pc_bundle_root() / "VERSION",
        pc_bundle_root() / "VERSION.txt",
        runtime_root() / "VERSION",
        runtime_root() / "VERSION.txt",
    ]

    for path in search_paths:
        if path.exists():
            try:
                version_str = path.read_text(encoding="utf-8").strip().lstrip("\ufeff")
                if version_str:
                    return version_str
            except Exception:
                pass

    return "未知版本"
