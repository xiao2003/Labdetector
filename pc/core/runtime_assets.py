#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""运行时资产目录管理。"""

from __future__ import annotations

import os
from pathlib import Path

from pc.app_identity import APP_NAME, launcher_root


DEFAULT_OLLAMA_MODELS = [
    "gemma3:4b",
    "llama3.2-vision:11b",
    "qwen3.5:4b",
    "qwen3.5:9b",
    "qwen3.5:27b",
    "qwen3.5:35b",
]


# 面向普通性能电脑的本地推理预设：
# 1. Ollama 模型本身已经是量化版本，这里不再重复做“量化”动作；
# 2. 通过压缩上下文窗口和生成长度，降低显存占用与首 token 等待时间；
# 3. 高参数量模型仍然保留，但默认只给更保守的推理预算。
OLLAMA_MODEL_OPTIONS = {
    "gemma3:4b": {
        "temperature": 0.2,
        "num_ctx": 4096,
        "num_predict": 192,
        "repeat_penalty": 1.05,
    },
    "llama3.2-vision:11b": {
        "temperature": 0.2,
        "num_ctx": 4096,
        "num_predict": 160,
        "repeat_penalty": 1.05,
    },
    "qwen3.5:4b": {
        "temperature": 0.2,
        "num_ctx": 4096,
        "num_predict": 192,
        "repeat_penalty": 1.05,
    },
    "qwen3.5:9b": {
        "temperature": 0.2,
        "num_ctx": 3072,
        "num_predict": 160,
        "repeat_penalty": 1.05,
    },
    "qwen3.5:27b": {
        "temperature": 0.2,
        "num_ctx": 2048,
        "num_predict": 128,
        "repeat_penalty": 1.08,
    },
    "qwen3.5:35b": {
        "temperature": 0.2,
        "num_ctx": 2048,
        "num_predict": 96,
        "repeat_penalty": 1.08,
    },
}


def ollama_model_options(model_name: str) -> dict[str, float | int]:
    """返回给 Ollama 的轻量推理预设。"""
    return dict(OLLAMA_MODEL_OPTIONS.get(str(model_name or "").strip(), {}))


def app_runtime_data_root() -> Path:
    """返回运行时可写数据目录，不把大模型落回源码仓库。"""
    local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
    if local_app_data:
        root = Path(local_app_data) / APP_NAME
    else:
        root = launcher_root() / "_runtime_data"
    root.mkdir(parents=True, exist_ok=True)
    return root


def speech_asset_root() -> Path:
    root = app_runtime_data_root() / "speech_assets"
    root.mkdir(parents=True, exist_ok=True)
    return root


def vosk_model_dir() -> Path:
    path = speech_asset_root() / "vosk-model-small-cn-0.22"
    path.mkdir(parents=True, exist_ok=True)
    return path


def sensevoice_model_dir() -> Path:
    path = speech_asset_root() / "SenseVoiceSmall"
    path.mkdir(parents=True, exist_ok=True)
    return path
