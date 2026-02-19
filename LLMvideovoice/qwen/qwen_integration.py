#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Qwen3.5-Plus API 集成模块
此模块提供与阿里云通义千问API的集成功能
"""

import base64
import json
import requests
from typing import Optional, Dict, Any


class QwenAnalyzer:
    """
    Qwen3.5-Plus 分析器
    提供与阿里云通义千问API的集成
    """
    
    def __init__(self, api_key: str, endpoint: str = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"):
        """
        初始化Qwen分析器
        
        Args:
            api_key: 阿里云API密钥
            endpoint: API端点URL
        """
        self.api_key = api_key
        self.endpoint = endpoint
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
    def analyze_image(self, image_bytes: bytes, prompt: str = "请详细描述这张图片的内容") -> Optional[Dict[Any, Any]]:
        """
        使用Qwen3.5-Plus分析图像
        
        Args:
            image_bytes: 图像字节数据
            prompt: 分析提示词
            
        Returns:
            API响应字典或None
        """
        # 将图像转换为base64
        image_base64 = base64.b64encode(image_bytes).decode('utf-8')
        
        # 构建请求载荷
        payload = {
            "model": "qwen-vl-max",  # 使用支持图像理解的模型
            "input": {
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "image": f"data:image/jpeg;base64,{image_base64}"
                            },
                            {
                                "text": prompt
                            }
                        ]
                    }
                ]
            },
            "parameters": {
                "temperature": 0.1,
                "max_tokens": 500
            }
        }
        
        try:
            response = requests.post(
                self.endpoint,
                headers=self.headers,
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                return result
            else:
                print(f"[ERROR] Qwen API请求失败: {response.status_code}, {response.text}")
                return None
                
        except requests.exceptions.RequestException as e:
            print(f"[ERROR] Qwen API请求异常: {str(e)}")
            return None
        except Exception as e:
            print(f"[ERROR] Qwen分析过程异常: {str(e)}")
            return None
    
    def extract_description(self, api_response: Dict[Any, Any]) -> str:
        """
        从API响应中提取描述文本
        
        Args:
            api_response: API响应字典
            
        Returns:
            提取的描述文本
        """
        try:
            # 根据API响应格式提取文本
            if 'output' in api_response and 'choices' in api_response['output']:
                choices = api_response['output']['choices']
                if choices and len(choices) > 0:
                    message_content = choices[0].get('message', {}).get('content', [])
                    if isinstance(message_content, list):
                        # 查找文本类型的content
                        for item in message_content:
                            if item.get('text'):
                                return item['text'].strip()
                    elif isinstance(message_content, str):
                        return message_content.strip()
            return "Qwen分析失败：无法提取响应内容"
        except Exception as e:
            print(f"[ERROR] 提取Qwen响应内容失败: {str(e)}")
            return "Qwen分析失败：响应格式异常"


# 示例函数，展示如何将Qwen集成到现有代码中
def integrate_qwen_with_existing_system():
    """
    演示如何将Qwen分析功能集成到现有系统中
    """
    print("Qwen3.5-Plus 集成模块加载成功")
    print("使用方法：")
    print("1. 获取阿里云API密钥")
    print("2. 创建QwenAnalyzer实例")
    print("3. 在图像分析流程中调用Qwen分析")
    
    # 示例用法
    # qwen_analyzer = QwenAnalyzer("your-api-key-here")
    # result = qwen_analyzer.analyze_image(image_bytes, "请描述图片内容")
    # description = qwen_analyzer.extract_description(result)


if __name__ == "__main__":
    integrate_qwen_with_existing_system()