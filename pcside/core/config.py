#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pcside/core/config.py - 全局配置管理 (根目录直达版)
"""
import configparser
import os
import threading
from typing import Any, Dict

# 获取项目根目录 (跨过 core 和 pcside)
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))

# ★ 强制将配置文件定位在项目根目录 D:\Labdetector\config.ini ★
config_path = os.path.join(project_root, 'config.ini')

_config: Dict[str, Any] = {}
_config_lock = threading.Lock()


def _create_default_config():
    """如果在根目录没找到，则自动生成一份极简默认配置"""
    parser = configparser.ConfigParser()

    parser['System'] = {
        'debug': 'False',
        'asset_dir': 'assets',
        'log_level': 'INFO'
    }

    parser['Network'] = {
        'broadcast_port': '50000',
        'websocket_port': '8001',
        'discovery_timeout': '3.0'
    }

    parser['Ollama'] = {
        'host': 'http://localhost:11434',
        'default_models': 'llava:7b-v1.5-q4_K_M, qwen-vl'
    }

    parser['VoiceInteraction'] = {
        'wake_word': '小爱同学',
        'wake_timeout': '10',
        'wake_threshold': '0.01',
        'energy_threshold': '300',
        'pause_threshold': '0.8',
        'online_recognition': 'True'
    }

    with open(config_path, 'w', encoding='utf-8') as f:
        parser.write(f)


def load_config():
    global _config
    with _config_lock:
        if not os.path.exists(config_path):
            _create_default_config()

        parser = configparser.ConfigParser()
        parser.read(config_path, encoding='utf-8')

        _config.clear()
        for section in parser.sections():
            for key, value in parser.items(section):
                config_key = f"{section.lower()}.{key}"
                _config[config_key] = value


def get_config(key: str, default: Any = None) -> Any:
    if not _config: load_config()
    return _config.get(key.lower(), default)


def set_config(key: str, value: Any):
    global _config
    if not _config: load_config()

    with _config_lock:
        _config[key.lower()] = str(value)
        parser = configparser.ConfigParser()
        if os.path.exists(config_path):
            parser.read(config_path, encoding='utf-8')

        parts = key.split('.')
        section = parts[0].capitalize()
        option = parts[1] if len(parts) > 1 else key

        if not parser.has_section(section):
            parser.add_section(section)
        parser.set(section, option, str(value))

        with open(config_path, 'w', encoding='utf-8') as f:
            parser.write(f)


# 初始化加载
load_config()