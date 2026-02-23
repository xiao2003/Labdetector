#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tools/version_manager.py - 全局版本号读取接口
"""
import os


def get_app_version() -> str:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(current_dir)
    grandparent_dir = os.path.dirname(parent_dir)

    # ★ 完美兼容 Windows 隐藏扩展名导致的 .txt 后缀问题
    search_paths = [
        os.path.join(grandparent_dir, "VERSION"),
        os.path.join(grandparent_dir, "VERSION.txt"),
        os.path.join(parent_dir, "VERSION"),
        os.path.join(parent_dir, "VERSION.txt")
    ]

    for path in search_paths:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    version_str = f.read().strip()
                    if version_str:
                        return version_str
            except Exception:
                pass

    return "未知版本"
