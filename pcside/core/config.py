#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pcside/core/config.py - 全局配置管理
"""
import configparser
import os
import threading
from typing import Any, Dict

# 获取项目根目录 (跨过 core 和 pcside)
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))

# ★ 配置文件路径：D:\Labdetector\config.ini
config_path = os.path.join(project_root, 'config.ini')

_config: Dict[str, Any] = {}
_config_lock = threading.Lock()


def _create_or_update_config():
    """
    核心逻辑：如果不存在则新建；如果存在则对比并覆盖/补全缺失项。
    """
    parser = configparser.ConfigParser()

    # 1. 如果文件已存在，先读取它
    if os.path.exists(config_path):
        parser.read(config_path, encoding='utf-8')

    # 2. 定义最新的默认配置结构 (包含你之前的 Ollama 模型列表)
    new_defaults = {
        'System': {
            'debug': 'False',
            'asset_dir': 'assets',
            'log_level': 'INFO'
        },
        'Network': {
            'broadcast_port': '50000',
            'websocket_port': '8001',
            'discovery_timeout': '3.0'
        },
        'Ollama': {
            'host': 'http://localhost:11434',
            # ★ 补回你之前的多模型列表 ★
            'default_models': 'llava:7b-v1.5-q4_K_M, llava:13b-v1.5-q4_K_M, llava:latest,  qwen-vl,'
        },
        'VoiceInteraction': {
            'wake_word': '小爱同学',
            'wake_timeout': '10',
            'energy_threshold': '300',
            'pause_threshold': '0.8',
            'online_recognition': 'True'
        }
    }

    # 3. 智能合并：如果 Section 或 Option 不存在，则添加；如果存在，保持原样（或根据需求强制覆盖）
    modified = False
    for section, options in new_defaults.items():
        if section not in parser:
            parser.add_section(section)
            modified = True
        for option, value in options.items():
            if option not in parser[section]:
                parser[section][option] = value
                modified = True

    # 4. 如果是新文件，或者内容有更新，则执行写入（'w' 模式会自动覆盖改写）
    if modified or not os.path.exists(config_path):
        with open(config_path, 'w', encoding='utf-8') as f:
            parser.write(f)
        # print(f"[INFO] 配置文件已更新: {config_path}")


def load_config():
    global _config
    with _config_lock:
        # ★ 每次启动都执行“检查并更新”逻辑，确保代码中的新默认值能进到 .ini 里 ★
        _create_or_update_config()

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