#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""core/logger.py - 日志管理模块"""

from __future__ import annotations

import sys
import threading
from datetime import datetime


def _supports_tty(stream: object) -> bool:
    try:
        return bool(stream) and bool(getattr(stream, 'isatty', lambda: False)())
    except Exception:
        return False


_COLOR_ENABLED = _supports_tty(sys.stdout)
COLOR_RED = '\033[91m' if _COLOR_ENABLED else ''
COLOR_WHITE = '\033[0m' if _COLOR_ENABLED else ''
COLOR_RESET = '\033[0m' if _COLOR_ENABLED else ''

print_lock = threading.Lock()
_status_line = ''


def _get_timestamp() -> str:
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def _safe_print(text: str, *, end: str = '\n', flush: bool = False) -> None:
    stream = sys.stdout or sys.__stdout__
    if stream is None:
        return
    try:
        print(text, end=end, flush=flush, file=stream)
    except Exception:
        pass


def console_info(text: str) -> None:
    global _status_line
    with print_lock:
        if _status_line:
            _safe_print('\r' + ' ' * len(_status_line), end='\r', flush=True)
        _safe_print(f'{COLOR_WHITE}[INFO] {text}{COLOR_RESET}')
        if _status_line:
            _safe_print('\r' + _status_line, end='', flush=True)


def console_error(text: str) -> None:
    global _status_line
    timestamp = _get_timestamp()
    with print_lock:
        if _status_line:
            _safe_print('\r' + ' ' * len(_status_line), end='\r', flush=True)
        _safe_print(f'{COLOR_RED}{timestamp} [ERROR] {text}{COLOR_RESET}')
        if _status_line:
            _safe_print('\r' + _status_line, end='', flush=True)


def console_prompt(text: str) -> None:
    global _status_line
    with print_lock:
        if _status_line:
            _safe_print('\r' + ' ' * len(_status_line), end='\r', flush=True)
        _safe_print(text)
        if _status_line:
            _safe_print('\r' + _status_line, end='', flush=True)


def console_status(text: str) -> None:
    global _status_line
    with print_lock:
        _status_line = text
        _safe_print('\r' + text, end='', flush=True)
