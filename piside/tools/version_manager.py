#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tools/version_manager.py - 全局版本号读取接口
"""
import os


def get_app_version() -> str:
    """
    智能向上层目录寻找 VERSION 文件并返回版本号字符串。
    即使被打包或单独拷贝到树莓派，也能自动定位。
    """
    # 当前文件所在目录: tools/
    current_dir = os.path.dirname(os.path.abspath(__file__))

    # 定义可能存放 VERSION 文件的路径列表：
    # 1. 父目录 (例如单机部署时的 piside/ 或 pcside/ 根目录)
    # 2. 爷爷目录 (开发环境下的整个 Labdetector 项目根目录)
    search_paths = [
        os.path.join(os.path.dirname(current_dir), "VERSION"),
        os.path.join(os.path.dirname(os.path.dirname(current_dir)), "VERSION")
    ]

    for path in search_paths:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    version_str = f.read().strip()
                    if version_str:
                        return version_str
            except Exception as e:
                print(f"[WARN] 读取 VERSION 文件失败: {e}")

    return "[WARN] 未知版本 (找不到 VERSION 文件)"