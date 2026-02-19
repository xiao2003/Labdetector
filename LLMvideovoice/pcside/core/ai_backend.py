#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/ai_backend.py - AI后端管理模块
"""

import requests
import base64
import cv2
import os
from core.config import get_config
from core.logger import console_info, console_error


def list_ollama_models():
    """获取本地已安装的Ollama模型列表"""
    try:
        resp = requests.get(f"{get_config('ollama.host')}/api/tags", timeout=5)
        if resp.status_code == 200:
            local_models = [m.get("name") for m in resp.json().get("models", []) if "llava" in m.get("name", "")]
            return local_models
    except Exception as e:
        console_error(f"获取Ollama模型列表失败: {str(e)}")
    return []


def analyze_image(frame, model, timeout=20):
    """
    使用AI模型分析图像
    Args:
        frame: 图像帧
        model: 模型名称
        timeout: 超时时间
    Returns:
        分析结果文本
    """
    # 使用Ollama分析
    try:
        _, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
        b64 = base64.b64encode(buf).decode()
        prompt = """请精准描述画面内容，控制在15字以内，仅返回描述文本"""
        payload = {
            "model": model,
            "prompt": prompt,
            "images": [b64],
            "stream": False,
            "options": {
                "temperature": 0.01,
                "num_predict": 100,
                "top_p": 0.1,
                "gpu_layers": get_config("gpu.layers", 35)
            }
        }
        resp = requests.post(
            f"{get_config('ollama.host')}/api/generate",
            json=payload,
            timeout=timeout
        )
        if resp.status_code == 200:
            result = resp.json()["response"].strip().replace("\n", "").replace(" ", "")[:15]
            console_info(f"Ollama识别结果: {result}")
            return result
        else:
            console_error(f"Ollama识别失败: HTTP {resp.status_code}")
    except Exception as e:
        console_error(f"Ollama推理异常: {str(e)[:50]}")

    return "识别失败"


def analyze_text(text, model, api_key=None):
    """
    使用AI模型分析文本
    Args:
        text: 文本内容
        model: 模型名称
        api_key: API密钥（用于Qwen）
    Returns:
        分析结果文本
    """
    # 检查是否是Qwen模型
    if "qwen" in model.lower():
        try:
            # 从环境变量或配置获取API密钥
            api_key = api_key or os.getenv("QWEN_API_KEY")
            if not api_key:
                import configparser
                config = configparser.ConfigParser()
                if config.read('config.ini') and 'qwen' in config and 'api_key' in config['qwen']:
                    api_key = config['qwen']['api_key']

            if api_key:
                from qwen_integration import QwenAnalyzer
                qwen_analyzer = QwenAnalyzer(api_key)
                # 使用Qwen的文本对话功能
                response = qwen_analyzer.chat(text)
                console_info(f"Qwen回复: {response}")
                return response
            else:
                return "Qwen API密钥未配置"
        except ImportError:
            return "Qwen模块缺失"
        except Exception as e:
            return f"Qwen处理出错: {str(e)[:50]}"

    # 使用Ollama进行文本分析
    try:
        payload = {
            "model": model,
            "prompt": text,
            "stream": False
        }
        resp = requests.post(
            f"{get_config('ollama.host')}/api/generate",
            json=payload,
            timeout=20
        )
        if resp.status_code == 200:
            return resp.json()["response"].strip()
        else:
            return "Ollama处理失败"
    except Exception as e:
        return f"Ollama处理出错: {str(e)[:50]}"