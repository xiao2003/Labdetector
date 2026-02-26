#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/ai_backend.py - AI后端接口
"""

import requests
import cv2
import numpy as np
import base64
from .config import get_config
from .logger import console_info, console_error
import os
import subprocess

def analyze_image(frame, model, prompt="请精准描述画面内容，控制在20字以内，仅返回描述文本"):
    if _STATE.get("ai_backend") == "ollama":
        return analyze_image_ollama(frame, model, prompt)
    elif _STATE.get("ai_backend") == "qwen":
        return analyze_image_qwen(frame, model, prompt)
    else:
        console_error("未知AI后端")
        return "未知AI后端"


def analyze_image_ollama(frame, model, prompt):
    """使用Ollama分析图像"""
    # 将OpenCV图像转换为JPG格式
    _, img_encoded = cv2.imencode('.jpg', frame)
    img_base64 = base64.b64encode(img_encoded).decode('utf-8')

    # 准备请求数据
    payload = {
        "model": model,
        "prompt": prompt,  # <--- ★ 这里改为动态使用传入的 prompt
        "images": [img_base64],
        "stream": False
    }

    try:
        # 发送请求到Ollama API
        resp = requests.post(
            f"{get_config('ollama.host')}/api/generate",
            json=payload,
            timeout=get_config("inference.timeout", 20)
        )

        if resp.status_code == 200:
            result = resp.json()["response"].strip()
            console_info(f"Ollama识别结果: {result}");
            return result
        else:
            console_error(f"Ollama API返回错误: {resp.status_code}")
            return "识别失败"
    except Exception as e:
        console_error(f"Ollama请求异常: {str(e)}")
        return "识别失败"


def analyze_image_qwen(frame, model, prompt):
    """使用Qwen分析图像"""
    try:
        # 将OpenCV图像转换为JPG格式
        _, img_encoded = cv2.imencode('.jpg', frame)
        img_bytes = img_encoded.tobytes()

        # 从环境变量获取API密钥
        api_key = os.getenv("QWEN_API_KEY")
        if not api_key:
            # 尝试从配置文件获取
            try:
                from config import get_config
                api_key = get_config("qwen.api_key")
            except:
                pass

        if not api_key:
            console_error("Qwen API密钥未配置")
            return "API密钥未配置"

        # 这里需要实现Qwen API调用
        # 以下是一个示例实现
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        # 将图像转换为base64
        img_base64 = base64.b64encode(img_bytes).decode('utf-8')

        payload = {
            "model": model,
            "input": {
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "image": f"data:image/jpeg;base64,{img_base64}"
                            },
                            {
                                "text": prompt
                            }
                        ]
                    }
                ]
            }
        }

        resp = requests.post(
            "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation",
            json=payload,
            headers=headers,
            timeout=get_config("inference.timeout", 20)
        )

        if resp.status_code == 200:
            response_data = resp.json()
            # 提取文本内容
            if "output" in response_data and "choices" in response_data["output"] and len(
                    response_data["output"]["choices"]) > 0:
                content = response_data["output"]["choices"][0]["message"]["content"]
                if isinstance(content, list):
                    text_content = " ".join([item["text"] for item in content if item["type"] == "text"])
                else:
                    text_content = content
                console_info(f"Qwen识别结果: {text_content}");
                return text_content
            else:
                console_error("Qwen API响应格式错误")
                return "识别失败"
        else:
            error_msg = resp.text
            console_error(f"Qwen API返回错误: {resp.status_code} - {error_msg[:50]}")
            return "识别失败"
    except Exception as e:
        console_error(f"Qwen请求异常: {str(e)}")
        return "识别失败"


# 添加全局状态
_STATE = {
    "ai_backend": ""
}


def set_ai_backend(backend: str):
    """设置AI后端"""
    _STATE["ai_backend"] = backend

    def list_ollama_models():
        """获取本地已安装的Ollama模型列表（备用实现）"""
        try:
            # 尝试使用Ollama命令行工具获取模型列表
            result = subprocess.run(['ollama', 'list'], capture_output=True, text=True)
            if result.returncode == 0:
                # 解析输出，获取模型列表
                lines = result.stdout.strip().split('\n')
                # 跳过标题行，只取模型名
                models = []
                for line in lines[1:]:
                    parts = line.split()
                    if parts:
                        models.append(parts[0])
                return models
        except Exception as e:
            console_error(f"获取Ollama模型列表失败: {str(e)}")
        return []


def list_ollama_models():
    """获取本地已安装的Ollama模型列表"""
    try:
        # 获取Ollama可执行文件路径
        ollama_exe = "ollama"
        default_path = "C:\\Users\\Administrator\\AppData\\Local\\Programs\\Ollama\\ollama.exe"
        if os.name == 'nt' and os.path.exists(default_path):
            ollama_exe = default_path

        # 尝试获取模型列表
        try:
            # 使用ollama list命令获取模型列表
            result = subprocess.run(
                [ollama_exe, "list"],
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode == 0:
                # 解析输出，获取模型列表
                lines = result.stdout.strip().split('\n')
                # 跳过标题行，只取模型名
                models = []
                for line in lines[1:]:
                    # 处理不同格式的输出
                    parts = line.split()
                    if parts and len(parts) > 0:
                        # 只取完整模型名称，如"llava:7b-v1.5-q4_K_M"
                        model_name = parts[0]
                        # 确保模型名包含冒号（:），避免基础名称"llava"
                        if ':' in model_name:
                            models.append(model_name)
                return models
        except subprocess.TimeoutExpired:
            pass
        except Exception as e:
            # 记录详细错误
            from logger import console_error
            console_error(f"获取Ollama模型列表失败: {str(e)}")

        # 如果命令行方式失败，尝试API方式
        try:
            resp = requests.get(f"{get_config('ollama.host')}/api/tags", timeout=5)
            if resp.status_code == 200:
                local_models = [m.get("name") for m in resp.json().get("models", [])
                                if "llava" in m.get("name", "")]
                return local_models
        except Exception as e:
            from logger import console_error
            console_error(f"通过API获取Ollama模型列表失败: {str(e)}")

    except Exception as e:
        from logger import console_error
        console_error(f"获取Ollama模型列表异常: {str(e)}")

    return []


def ask_assistant_with_rag(frame, question: str, rag_context: str, model_name: str) -> str:
    """
    终极多模态问答：结合当前视频画面、用户的语音问题、以及 RAG 检索到的知识
    """
    import base64
    import cv2
    import requests
    from pcside.core.config import get_config

    prompt = f"""你是一个专业的微纳流体力学实验室AI助手。
请结合我提供的【实时实验室画面】和下方的【实验室知识库背景】，回答我的问题。

【知识库背景信息】:
{rag_context if rag_context else "暂无相关背景知识。"}

【用户问题】:
{question}

请用简明扼要、专业的中文回答，不超过50个字，适合语音播报。"""

    # 如果有画面，则进行 Base64 编码
    images = []
    if frame is not None:
        try:
            _, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
            img_b64 = base64.b64encode(buffer).decode('utf-8')
            images.append(img_b64)
        except Exception:
            pass

    # 这里以 Ollama 为例调用
    host = get_config("ollama.host", "http://localhost:11434")
    try:
        payload = {
            "model": model_name,
            "prompt": prompt,
            "images": images,
            "stream": False,
            "options": {"temperature": 0.3}  # 降低温度保证回答的严谨性
        }
        resp = requests.post(f"{host}/api/generate", json=payload, timeout=60)
        resp.raise_for_status()
        return resp.json().get("response", "我暂时无法得出结论。")
    except Exception as e:
        return f"大脑思考异常: {str(e)[:30]}"