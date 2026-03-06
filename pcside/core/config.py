#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pcside/core/config.py - core configuration manager.
"""

from __future__ import annotations

import configparser
import os
from typing import Any


current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
config_file = os.path.join(project_root, "config.ini")

_config = configparser.ConfigParser()

_DEFAULT_CONFIG = {
    "ai_backend": {
        "type": "ollama",
    },
    "ollama": {
        "url": "http://127.0.0.1:11434",
        "api_base": "http://127.0.0.1:11434",
        "base_url": "http://127.0.0.1:11434",
        "default_models": "llava:13b-v1.5-q4_K_M, llava:7b-v1.5-q4_K_M, llava:latest, qwen-vl",
    },
    "qwen": {
        "model": "qwen-vl-max",
    },
    "voice_interaction": {
        "wake_word": "小爱同学",
        "wake_timeout": "10.0",
        "wake_threshold": "0.01",
        "energy_threshold": "300",
        "pause_threshold": "0.8",
        "online_recognition": "True",
        "vosk_model_path": os.path.join(project_root, "pcside", "voice", "model"),
    },
    "inference": {
        "interval": "5",
    },
    "expert_loop": {
        "ack_timeout": "2.0",
        "ack_retries": "2",
    },
    "shadow_demo": {
        "enabled": "False",
        "interval_seconds": "8",
    },
    "experts": {
    },
}


def _save_config() -> None:
    with open(config_file, "w", encoding="utf-8") as configfile:
        _config.write(configfile)


def _init_config() -> None:
    if os.path.exists(config_file):
        _config.read(config_file, encoding="utf-8")

    needs_save = False
    for section, options in _DEFAULT_CONFIG.items():
        if not _config.has_section(section):
            _config.add_section(section)
            needs_save = True

        for key, value in options.items():
            if not _config.has_option(section, key):
                _config.set(section, key, str(value))
                needs_save = True
                continue

            if key == "default_models":
                existing_val = _config.get(section, key)
                existing_list = [x.strip() for x in existing_val.split(",") if x.strip()]
                default_list = [x.strip() for x in str(value).split(",") if x.strip()]
                missing_items = [x for x in default_list if x not in existing_list]
                if missing_items:
                    _config.set(section, key, ", ".join(existing_list + missing_items))
                    needs_save = True

    if needs_save or not os.path.exists(config_file):
        _save_config()


_init_config()


def get_config(key: str, default: Any = None) -> Any:
    if default is None and "ollama" in key.lower() and any(x in key.lower() for x in ["url", "api", "base", "host"]):
        default = "http://127.0.0.1:11434"

    if "." in key:
        section, option = key.split(".", 1)
        if _config.has_section(section) and _config.has_option(section, option):
            val = _config.get(section, option)
            lowered = val.lower()
            if lowered in ["true", "yes", "on"]:
                return True
            if lowered in ["false", "no", "off"]:
                return False
            try:
                if "." in val:
                    return float(val)
                return int(val)
            except ValueError:
                return val
    return default


def set_config(key: str, value: Any) -> None:
    if "." in key:
        section, option = key.split(".", 1)
        if not _config.has_section(section):
            _config.add_section(section)
        _config.set(section, option, str(value))
        _save_config()
