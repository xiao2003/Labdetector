#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pc/core/config.py - core configuration manager."""

from __future__ import annotations

import configparser
import os
from typing import Any

from pc.app_identity import resource_path
from pc.core.runtime_assets import DEFAULT_OLLAMA_MODELS, sensevoice_model_dir, vosk_model_dir


project_root = str(resource_path("pc"))
config_file = str(resource_path("config.ini"))

_config = configparser.ConfigParser()

_DEFAULT_CONFIG = {
    "ai_backend": {
        "type": "ollama",
    },
    "ollama": {
        "url": "http://127.0.0.1:11434",
        "api_base": "http://127.0.0.1:11434",
        "base_url": "http://127.0.0.1:11434",
        "default_models": ", ".join(DEFAULT_OLLAMA_MODELS),
    },
    "local_llm": {
        "active_model": "",
        "active_adapter_path": "",
        "base_model": "",
        "generation_max_new_tokens": "192",
        "temperature": "0.3",
        "top_p": "0.9",
    },
    "orchestrator": {
        "enabled": "True",
        "model_name": "Qwen3.5-0.8B",
        "model_relpath": "pc/models/orchestrator/Qwen3.5-0.8B.q4_k_m.gguf",
        "runtime_relpath": "pc/runtime/llm_orchestrator/llama-cli.exe",
        "asset_manifest_relpath": "pc/models/orchestrator/orchestrator_assets.json",
        "timeout_seconds": "8",
        "temperature": "0.1",
        "top_p": "0.8",
        "top_k": "20",
        "num_ctx": "2048",
        "num_predict": "256",
    },
    "qwen": {
        "model": "qwen-vl-max",
        "api_key": "",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    },
    "openai_cloud": {
        "model": "gpt-4.1-mini",
        "api_key": "",
        "base_url": "https://api.openai.com/v1",
    },
    "deepseek_cloud": {
        "model": "deepseek-chat",
        "api_key": "",
        "base_url": "https://api.deepseek.com/v1",
    },
    "kimi_cloud": {
        "model": "moonshot-v1-128k",
        "api_key": "",
        "base_url": "https://api.moonshot.cn/v1",
    },
    "openai_compatible": {
        "model": "custom-model",
        "api_key": "",
        "base_url": "",
    },
    "lmstudio_local": {
        "model": "qwen2.5-vl-7b-instruct",
        "api_key": "",
        "base_url": "http://127.0.0.1:1234/v1",
    },
    "vllm_local": {
        "model": "Qwen/Qwen2.5-VL-7B-Instruct",
        "api_key": "",
        "base_url": "http://127.0.0.1:8000/v1",
    },
    "sglang_local": {
        "model": "Qwen/Qwen2.5-VL-7B-Instruct",
        "api_key": "",
        "base_url": "http://127.0.0.1:30000/v1",
    },
    "lmdeploy_local": {
        "model": "Qwen/Qwen2.5-VL-7B-Instruct",
        "api_key": "",
        "base_url": "http://127.0.0.1:23333/v1",
    },
    "xinference_local": {
        "model": "qwen2.5-vl-7b-instruct",
        "api_key": "",
        "base_url": "http://127.0.0.1:9997/v1",
    },
    "llamacpp_local": {
        "model": "qwen2.5-vl-7b-instruct",
        "api_key": "",
        "base_url": "http://127.0.0.1:8080/v1",
    },
    "voice_interaction": {
        "wake_word": "小爱同学",
        "wake_timeout": "10.0",
        "wake_threshold": "0.01",
        "energy_threshold": "300",
        "pause_threshold": "0.8",
        "wake_aliases": "小爱同学,小爱同,小爱,小艾同学,晓爱同学,哎同学,爱同学",
        "wake_phrase_time_limit": "4.0",
        "command_timeout": "6.0",
        "command_phrase_time_limit": "12.0",
        "online_recognition": "True",
        "asr_engine": "auto",
        "wake_engine": "auto",
        "funasr_model": str(sensevoice_model_dir()),
        "funasr_model_repo_id": "iic/SenseVoiceSmall",
        "funasr_vad_model": "",
        "funasr_punc_model": "",
        "funasr_device": "auto",
        "funasr_language": "zh",
        "funasr_use_itn": "False",
        "vosk_model_path": str(vosk_model_dir()),
        "openwakeword_model_path": "",
        "openwakeword_threshold": "0.45",
        "openwakeword_chunk_size": "1280",
    },
    "inference": {
        "interval": "5",
        "timeout": "20",
    },
    "expert_loop": {
        "ack_timeout": "2.0",
        "ack_retries": "2",
        "focus_codes": "safety.ppe_expert,safety.chem_safety_expert",
    },
    "network": {
        "virtual_pi_enabled": "False",
        "virtual_pi_host": "127.0.0.1",
        "virtual_pi_hosts": "",
    },
    "shadow_demo": {
        "enabled": "False",
        "interval_seconds": "8",
    },
    "desktop_ui": {
        "window_geometry": "",
        "window_state": "normal",
        "left_collapsed": "False",
        "demo_mode": "False",
    },
    "session_defaults": {
        "project_name": "AI4S 实验室智能监控",
        "experiment_name": "实验监控任务",
        "operator_name": "",
        "tags": "实验室,监控,AI4S",
    },
    "training": {
        "workspace_name": "labdetector_training",
        "llm_base_model": "",
        "llm_epochs": "1",
        "llm_batch_size": "1",
        "llm_learning_rate": "0.0002",
        "llm_lora_r": "8",
        "llm_lora_alpha": "16",
        "pi_base_weights": "yolov8n.pt",
        "pi_epochs": "20",
        "pi_imgsz": "640",
        "pi_device": "",
    },
    "self_check": {
        "pc_auto_install_core": "True",
        "pc_auto_install_training": "True",
        "pc_auto_install_optional": "False",
        "pc_auto_install_voice_ai": "True",
        "pc_auto_install_gpu_runtime": "True",
        "pc_auto_install_ollama": "True",
        "pi_auto_install_dependencies": "True",
    },
    "gpu_runtime": {
        "pytorch_cuda_index_url": "https://download.pytorch.org/whl/cu124",
        "pytorch_cuda_packages": "torch,torchvision,torchaudio",
        "auto_install_on_nvidia": "True",
    },
    "pi_detector": {
        "active_weights": "",
        "conf": "0.4",
        "imgsz": "640",
    },
    "experts": {},
}


def _save_config() -> None:
    config_dir = os.path.dirname(config_file)
    if config_dir:
        os.makedirs(config_dir, exist_ok=True)
    with open(config_file, "w", encoding="utf-8-sig") as configfile:
        _config.write(configfile)


def _init_config() -> None:
    if os.path.exists(config_file):
        _config.read(config_file, encoding="utf-8-sig")

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

    old_sensevoice_path = str(resource_path("pc/voice/models/SenseVoiceSmall"))
    new_sensevoice_path = str(sensevoice_model_dir())
    if _config.get("voice_interaction", "funasr_model", fallback="") == old_sensevoice_path:
        _config.set("voice_interaction", "funasr_model", new_sensevoice_path)
        needs_save = True

    old_vosk_path = str(resource_path("pc/voice/model"))
    new_vosk_path = str(vosk_model_dir())
    if _config.get("voice_interaction", "vosk_model_path", fallback="") == old_vosk_path:
        _config.set("voice_interaction", "vosk_model_path", new_vosk_path)
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
                if "." in val and all(ch.isdigit() or ch in {".", "-"} for ch in val.replace("e", "").replace("E", "")):
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
