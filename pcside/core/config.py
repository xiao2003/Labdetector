#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/config.py - 全局配置管理模块
"""

import os
import configparser
from typing import Union, Tuple, List
import socket


class Config:
    """全局配置类，提供只读访问"""
    _config = None
    _config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.ini')

    @classmethod
    def init(cls):
        """初始化配置，从配置文件加载或创建默认配置"""
        if cls._config is not None:
            return

        cls._config = configparser.ConfigParser()

        # 如果配置文件不存在，创建默认配置
        if not os.path.exists(cls._config_path):
            cls._create_default_config()

        # 读取配置文件
        cls._config.read(cls._config_path, encoding='utf-8')

        # 确保所有必要的部分都存在
        cls._ensure_sections()

    @classmethod
    def _create_default_config(cls):
        """创建默认配置文件"""
        config = configparser.ConfigParser()

        # voice_interaction 部分
        config['voice_interaction'] = {
            'wake_word': '小爱同学',
            'wake_timeout': '10',
            'wake_threshold': '0.01',
            'energy_threshold': '300',
            'pause_threshold': '0.8',
            'auto_start': 'True',
            'online_recognition': 'True'
        }

        # camera 部分
        config['camera'] = {
            'index': '0',
            'resolution': '1280,720'
        }

        # ollama 部分
        config['ollama'] = {
            'host': 'http://localhost:11434',
            'default_models': 'llava:7b-v1.5-q4_K_M,llava:13b-v1.5-q4_K_M,llava:34b-v1.5-q4_K_M,llava:latest'
        }

        # inference 部分
        config['inference'] = {
            'interval': '5',
            'timeout': '20'
        }

        # gpu 部分
        config['gpu'] = {
            'layers': '35'
        }

        # websocket 部分
        config['websocket'] = {
            'host': '192.168.31.31',
            'port': '8001'
        }

        # display 部分
        config['display'] = {
            'width': '1920',
            'height': '1080'
        }

        # ws_retry 部分
        config['ws_retry'] = {
            'max_attempts': '5',
            'interval': '3'
        }

        # network 部分
        config['network'] = {
            'local_ip': '',
            'pi_ip': '192.168.31.31',
            'discovery_port': '50000'
        }

        # 创建配置文件目录（如果不存在）
        config_dir = os.path.dirname(cls._config_path)
        if not os.path.exists(config_dir):
            os.makedirs(config_dir, exist_ok=True)

        # 写入配置文件
        with open(cls._config_path, 'w', encoding='utf-8') as configfile:
            config.write(configfile)

        print(f"[INFO] 创建默认配置文件: {cls._config_path}")

    @classmethod
    def _ensure_sections(cls):
        """确保所有必要的配置部分都存在"""
        required_sections = [
            'voice_interaction', 'camera', 'ollama', 'inference',
            'gpu', 'websocket', 'display', 'ws_retry', 'network'
        ]

        for section in required_sections:
            if section not in cls._config:
                cls._config[section] = {}

        # 确保所有必要的键都存在
        cls._ensure_voice_interaction_keys()
        cls._ensure_camera_keys()
        cls._ensure_ollama_keys()
        cls._ensure_inference_keys()
        cls._ensure_gpu_keys()
        cls._ensure_websocket_keys()
        cls._ensure_display_keys()
        cls._ensure_ws_retry_keys()
        cls._ensure_network_keys()

    @classmethod
    def _ensure_voice_interaction_keys(cls):
        """确保 voice_interaction 部分的所有键都存在"""
        section = 'voice_interaction'
        defaults = {
            'wake_word': '小爱同学',
            'wake_timeout': '10',
            'wake_threshold': '0.01',
            'energy_threshold': '300',
            'pause_threshold': '0.8',
            'auto_start': 'True',
            'online_recognition': 'True'
        }

        for key, value in defaults.items():
            if key not in cls._config[section]:
                cls._config[section][key] = value

    @classmethod
    def _ensure_camera_keys(cls):
        """确保 camera 部分的所有键都存在"""
        section = 'camera'
        defaults = {
            'index': '0',
            'resolution': '1280,720'
        }

        for key, value in defaults.items():
            if key not in cls._config[section]:
                cls._config[section][key] = value

    @classmethod
    def _ensure_ollama_keys(cls):
        """确保 ollama 部分的所有键都存在"""
        section = 'ollama'
        defaults = {
            'host': 'http://localhost:11434',
            'default_models': 'llava:7b-v1.5-q4_K_M,llava:13b-v1.5-q4_K_M,llava:34b-v1.5-q4_K_M,llava:latest'
        }

        for key, value in defaults.items():
            if key not in cls._config[section]:
                cls._config[section][key] = value

    @classmethod
    def _ensure_inference_keys(cls):
        """确保 inference 部分的所有键都存在"""
        section = 'inference'
        defaults = {
            'interval': '5',
            'timeout': '20'
        }

        for key, value in defaults.items():
            if key not in cls._config[section]:
                cls._config[section][key] = value

    @classmethod
    def _ensure_gpu_keys(cls):
        """确保 gpu 部分的所有键都存在"""
        section = 'gpu'
        defaults = {
            'layers': '35'
        }

        for key, value in defaults.items():
            if key not in cls._config[section]:
                cls._config[section][key] = value

    @classmethod
    def _ensure_websocket_keys(cls):
        """确保 websocket 部分的所有键都存在"""
        section = 'websocket'
        defaults = {
            'host': '192.168.31.31',
            'port': '8001'
        }

        for key, value in defaults.items():
            if key not in cls._config[section]:
                cls._config[section][key] = value

    @classmethod
    def _ensure_display_keys(cls):
        """确保 display 部分的所有键都存在"""
        section = 'display'
        defaults = {
            'width': '1920',
            'height': '1080'
        }

        for key, value in defaults.items():
            if key not in cls._config[section]:
                cls._config[section][key] = value

    @classmethod
    def _ensure_ws_retry_keys(cls):
        """确保 ws_retry 部分的所有键都存在"""
        section = 'ws_retry'
        defaults = {
            'max_attempts': '5',
            'interval': '3'
        }

        for key, value in defaults.items():
            if key not in cls._config[section]:
                cls._config[section][key] = value

    @classmethod
    def _ensure_network_keys(cls):
        """确保 network 部分的所有键都存在"""
        section = 'network'
        defaults = {
            'local_ip': '',
            'pi_ip': '192.168.31.31',
            'discovery_port': '50000'
        }

        for key, value in defaults.items():
            if key not in cls._config[section]:
                cls._config[section][key] = value

    @classmethod
    def get(cls, key_path: str, default=None) -> Union[str, int, float, bool, Tuple, List, None]:
        """
        获取配置值，支持路径访问（如"camera.resolution"）
        Args:
            key_path: 配置路径
            default: 默认值
        Returns:
            配置值或默认值
        """
        cls.init()  # 确保配置已初始化

        keys = key_path.split('.')
        if len(keys) < 2:
            return default

        section = keys[0]
        key = '.'.join(keys[1:])

        if section not in cls._config:
            return default

        if key not in cls._config[section]:
            return default

        value = cls._config[section][key]

        # 尝试将值转换为适当的类型
        try:
            # 尝试转换为整数
            return int(value)
        except ValueError:
            pass

        try:
            # 尝试转换为浮点数
            return float(value)
        except ValueError:
            pass

        if value.lower() == 'true':
            return True
        if value.lower() == 'false':
            return False

        # 特殊处理分辨率
        if section == 'camera' and key == 'resolution':
            try:
                parts = [int(x.strip()) for x in value.split(',')]
                if len(parts) == 2:
                    return (parts[0], parts[1])
            except:
                pass

        # 特殊处理默认模型列表
        if section == 'ollama' and key == 'default_models':
            return [x.strip() for x in value.split(',')]

        # 返回原始字符串
        return value

    @classmethod
    def set(cls, key_path: str, value):
        """
        设置配置值，支持路径访问
        Args:
            key_path: 配置路径
            value: 新值
        """
        cls.init()  # 确保配置已初始化

        keys = key_path.split('.')
        if len(keys) < 2:
            return

        section = keys[0]
        key = '.'.join(keys[1:])

        # 确保 section 存在
        if section not in cls._config:
            cls._config[section] = {}

        # 转换值为字符串
        if isinstance(value, bool):
            value = str(value)
        elif isinstance(value, (tuple, list)):
            value = ','.join(str(x) for x in value)
        else:
            value = str(value)

        cls._config[section][key] = value

        # 保存到配置文件
        cls._save_config()

    @classmethod
    def _save_config(cls):
        """将配置保存到文件"""
        try:
            with open(cls._config_path, 'w', encoding='utf-8') as configfile:
                cls._config.write(configfile)
        except Exception as e:
            print(f"[ERROR] 保存配置文件失败: {str(e)}")

    @classmethod
    def get_network_config(cls) -> dict:
        """获取网络配置"""
        cls.init()
        section = 'network'
        return {
            'local_ip': cls.get('network.local_ip', ''),
            'pi_ip': cls.get('network.pi_ip', '192.168.31.31'),
            'discovery_port': cls.get('network.discovery_port', 50000)
        }

    @classmethod
    def set_network_config(cls, local_ip: str = None, pi_ip: str = None):
        """设置网络配置"""
        if local_ip is not None:
            cls.set('network.local_ip', local_ip)
        if pi_ip is not None:
            cls.set('network.pi_ip', pi_ip)


# 初始化配置
Config.init()


# 简单的全局访问接口
def get_config(key_path: str, default=None):
    return Config.get(key_path, default)


def set_config(key_path: str, value):
    Config.set(key_path, value)


def get_network_config():
    """获取网络配置"""
    return Config.get_network_config()


def set_network_config(local_ip: str = None, pi_ip: str = None):
    """设置网络配置"""
    Config.set_network_config(local_ip, pi_ip)