#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/logger.py - 日志管理模块
"""

import threading
import sys
from datetime import datetime

# ANSI 转义序列用于颜色控制
COLOR_RED = '\033[91m' if sys.stdout.isatty() else ''
COLOR_WHITE = '\033[0m' if sys.stdout.isatty() else ''
COLOR_RESET = '\033[0m' if sys.stdout.isatty() else ''

# 日志相关
print_lock = threading.Lock()
_status_line = ""


def _get_timestamp():
    """获取当前时间戳字符串"""
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def console_info(text: str):
    """打印一条信息行，前缀 [INFO]，白色字体"""
    global _status_line
    with print_lock:
        # 清除状态行（覆盖为空格），再打印信息行
        if _status_line:
            try:
                print('\r' + ' ' * len(_status_line), end='\r', flush=True)
            except Exception:
                pass

        # 打印信息行（带[INFO]前缀，白色字体）
        print(f"{COLOR_WHITE}[INFO] {text}{COLOR_RESET}")

        # 恢复状态行显示（不换行）
        if _status_line:
            try:
                print('\r' + _status_line, end='', flush=True)
            except Exception:
                pass


def console_error(text: str):
    """打印一条错误信息行，前缀 [ERROR]，带时间戳，红色字体"""
    global _status_line
    timestamp = _get_timestamp()
    with print_lock:
        if _status_line:
            try:
                print('\r' + ' ' * len(_status_line), end='\r', flush=True)
            except Exception:
                pass

        # 打印错误行（带时间戳，红色字体）
        print(f"{COLOR_RED}{timestamp} [ERROR] {text}{COLOR_RESET}")

        if _status_line:
            try:
                print('\r' + _status_line, end='', flush=True)
            except Exception:
                pass


def console_prompt(text: str):
    """打印提示信息，不带任何前缀，用于用户交互提示"""
    global _status_line
    with print_lock:
        # 清除状态行（覆盖为空格），再打印信息行
        if _status_line:
            try:
                print('\r' + ' ' * len(_status_line), end='\r', flush=True)
            except Exception:
                pass

        # 打印提示信息（无前缀）
        print(text)

        # 恢复状态行显示（不换行）
        if _status_line:
            try:
                print('\r' + _status_line, end='', flush=True)
            except Exception:
                pass


def console_status(text: str):
    """在同一行显示实时状态（不换行）"""
    global _status_line
    with print_lock:
        _status_line = text
        try:
            print('\r' + text, end='', flush=True)
        except Exception:
            print(text)