#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pcside/core/config.py - 核心配置管理器 (支持动态插件配置与智能无损合并)
"""
import os
import configparser
from typing import Any

current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
config_file = os.path.join(project_root, 'config.ini')

_config = configparser.ConfigParser()

# 默认配置结构
_DEFAULT_CONFIG = {
    'ai_backend': {
        'type': 'ollama'
    },
    'ollama': {
        'api_base': 'http://127.0.0.1:11434',  # <--- 新增：补全缺失的 API 地址
        'default_models': 'llava:13b-v1.5-q4_K_M, llava:7b-v1.5-q4_K_M, llava:latest, qwen-vl'
    },
    'qwen': {
        'model': 'qwen-vl-max'
    },
    'voice_interaction': {
        'wake_word': '小爱同学',
        'wake_timeout': '10.0',
        'wake_threshold': '0.01',
        'energy_threshold': '300',
        'pause_threshold': '0.8',
        'online_recognition': 'True',
        'vosk_model_path': os.path.join(project_root, 'pcside', 'voice', 'model')
    },
    'inference': {
        'interval': '5'
    },
    'experts': {
        # 专家开关默认配置，扫描时会自动补充
    }
}


def _save_config():
    """将内存中的配置写入到文件"""
    with open(config_file, 'w', encoding='utf-8') as configfile:
        _config.write(configfile)


def _init_config():
    """初始化配置文件，智能对比、补充缺失的 section/key，并无损合并列表项"""
    if os.path.exists(config_file):
        _config.read(config_file, encoding='utf-8')

    needs_save = False
    for section, options in _DEFAULT_CONFIG.items():
        # 1. 补全缺失的区块 (Section)
        if not _config.has_section(section):
            _config.add_section(section)
            needs_save = True

        for key, value in options.items():
            # 2. 补全完全缺失的键 (Key)
            if not _config.has_option(section, key):
                _config.set(section, key, str(value))
                needs_save = True
            else:
                # 3. 智能对比：针对列表类型的配置（如 default_models）进行无损合并追加
                if key in ['default_models']:
                    existing_val = _config.get(section, key)
                    # 将现有的和默认的拆分成列表
                    existing_list = [x.strip() for x in existing_val.split(',') if x.strip()]
                    default_list = [x.strip() for x in str(value).split(',') if x.strip()]

                    # 找出官方默认里有，但用户当前配置里没有的新模型
                    missing_items = [x for x in default_list if x not in existing_list]

                    if missing_items:
                        # 把缺失的新模型追加到原有列表的后面
                        merged_list = existing_list + missing_items
                        _config.set(section, key, ", ".join(merged_list))
                        needs_save = True

    # 只有当发生过修改或文件不存在时才执行写入，避免无意义的磁盘IO
    if needs_save or not os.path.exists(config_file):
        _save_config()


# 在函数全部定义完毕后再执行初始化
_init_config()


def get_config(key: str, default: Any = None) -> Any:
    """
    获取配置值。支持 section.key 格式，如 'experts.danger_expert'
    """
    if '.' in key:
        section, option = key.split('.', 1)
        if _config.has_section(section) and _config.has_option(section, option):
            val = _config.get(section, option)
            # 尝试转换布尔值或数字
            if val.lower() in ['true', 'yes', 'on']: return True
            if val.lower() in ['false', 'no', 'off']: return False
            try:
                if '.' in val:
                    return float(val)
                return int(val)
            except ValueError:
                return val
    return default


def set_config(key: str, value: Any) -> None:
    """
    设置配置值并保存到文件。支持 section.key 格式。
    如果 section 不存在会自动创建。
    """
    if '.' in key:
        section, option = key.split('.', 1)
        if not _config.has_section(section):
            _config.add_section(section)
        _config.set(section, option, str(value))
        _save_config()