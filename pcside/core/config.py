#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/config.py - 全局配置管理模块 (多节点与 AI 实验室助手增强版)
"""

import os
import configparser
import json
from typing import Union, Tuple, List


class Config:
    """全局配置类，提供跨模块的持久化配置访问"""
    _config = None
    # 路径锁定在 pcside/core/config.ini
    _config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.ini')

    @classmethod
    def init(cls):
        """初始化配置，从配置文件加载或创建默认配置"""
        if cls._config is not None:
            return

        cls._config = configparser.ConfigParser()

        # 如果配置文件不存在，创建包含新字段的默认配置
        if not os.path.exists(cls._config_path):
            cls._create_default_config()

        # 读取配置文件
        cls._config.read(cls._config_path, encoding='utf-8')
        cls._ensure_sections()

    @classmethod
    def _create_default_config(cls):
        """创建工业级默认配置文件，涵盖多节点与 RAG 需求"""
        config = configparser.ConfigParser()

        # 1. 语音交互：支持唤醒与在线识别
        config['voice_interaction'] = {
            'wake_word': '小爱同学',
            'wake_timeout': '10',
            'online_recognition': 'True'
        }

        # 2. 网络与多节点拓扑：支持 1-5 台树莓派自动发现
        config['network'] = {
            'discovery_port': '50000',
            'default_pi_port': '8001',
            'local_ip': '',
            # multi_pis 以 JSON 字符串形式存储扫描到的 {ID: IP}
            'multi_pis': '{}'
        }

        # 3. 云端大模型：Qwen-VL 视觉增强接口
        config['qwen'] = {
            'api_key': 'YOUR_API_KEY_HERE',
            'model': 'qwen-vl-max'
        }

        # 4. 知识库 RAG：为后期学术资产化预留
        config['knowledge_base'] = {
            'vector_db_host': 'localhost',
            'vector_db_port': '19530',
            'embedding_model': 'shibing624/text2vec-base-chinese'
        }

        # 5. 视觉语义引擎：YOLO 检测与姿态分析
        config['vision'] = {
            'yolo_model': 'models/lab_yolo.pt',
            'confidence_threshold': '0.5',
            'enable_pose': 'True'
        }

        # 6. 路径管理：集中化日志与资产存储
        config['path'] = {
            'log_dir': 'log',
            'asset_dir': 'assets'
        }

        # 确保目录存在并写入
        os.makedirs(os.path.dirname(cls._config_path), exist_ok=True)
        with open(cls._config_path, 'w', encoding='utf-8') as f:
            config.write(f)
        print(f"[INFO] 已生成新版默认配置文件: {cls._config_path}")

    @classmethod
    def _ensure_sections(cls):
        """确保所有必要的 Section 都在 ini 中存在"""
        required = ['voice_interaction', 'network', 'qwen', 'knowledge_base', 'vision', 'path']
        for section in required:
            if section not in cls._config:
                cls._config[section] = {}

    @classmethod
    def get(cls, key_path: str, default=None):
        """获取配置值，支持 JSON 自动解析"""
        cls.init()
        keys = key_path.split('.')
        if len(keys) < 2: return default

        section, key = keys[0], '.'.join(keys[1:])
        if section not in cls._config or key not in cls._config[section]:
            return default

        value = cls._config[section][key]

        # 类型转换逻辑
        if value.lower() == 'true': return True
        if value.lower() == 'false': return False

        try:
            return int(value)
        except ValueError:
            pass

        # 自动解析 JSON (如 multi_pis)
        if (value.startswith('{') and value.endswith('}')) or (value.startswith('[') and value.endswith(']')):
            try:
                return json.loads(value)
            except:
                pass

        return value

    @classmethod
    def set(cls, key_path: str, value):
        """设置配置值，支持对象自动转 JSON"""
        cls.init()
        keys = key_path.split('.')
        if len(keys) < 2: return

        section, key = keys[0], '.'.join(keys[1:])
        if isinstance(value, (dict, list)):
            value = json.dumps(value)
        else:
            value = str(value)

        if section not in cls._config:
            cls._config[section] = {}
        cls._config[section][key] = value

        # 实时保存到文件
        with open(cls._config_path, 'w', encoding='utf-8') as f:
            cls._config.write(f)


# 全局访问接口
def get_config(key_path: str, default=None):
    return Config.get(key_path, default)


def set_config(key_path: str, value):
    Config.set(key_path, value)