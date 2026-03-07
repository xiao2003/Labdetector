from __future__ import annotations

import base64
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Tuple

import cv2
import requests

from pc.core.config import get_config, set_config
from pc.core.logger import console_error, console_info
from pc.training.model_linker import model_linker

PROVIDER_PRESETS: Dict[str, Dict[str, str]] = {
    "ollama": {
        "label": "Ollama（本地私有化模型）",
        "section": "ollama",
        "model_key": "default_model",
        "default_model": "llava:7b-v1.5-q4_K_M",
        "base_url": "http://127.0.0.1:11434",
    },
    "local_adapter": {
        "label": "本地微调适配器（Transformers + PEFT）",
        "section": "local_llm",
        "model_key": "active_model",
        "default_model": "",
        "base_url": "",
    },
    "qwen": {
        "label": "通义千问（阿里云）",
        "section": "qwen",
        "model_key": "model",
        "default_model": "qwen-vl-max",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    },
    "openai": {
        "label": "OpenAI 云模型",
        "section": "openai_cloud",
        "model_key": "model",
        "default_model": "gpt-4.1-mini",
        "base_url": "https://api.openai.com/v1",
    },
    "deepseek": {
        "label": "DeepSeek 云模型",
        "section": "deepseek_cloud",
        "model_key": "model",
        "default_model": "deepseek-chat",
        "base_url": "https://api.deepseek.com/v1",
    },
    "kimi": {
        "label": "Kimi / Moonshot 云模型",
        "section": "kimi_cloud",
        "model_key": "model",
        "default_model": "moonshot-v1-128k",
        "base_url": "https://api.moonshot.cn/v1",
    },
    "openai_compatible": {
        "label": "兼容 OpenAI 协议云模型",
        "section": "openai_compatible",
        "model_key": "model",
        "default_model": "custom-model",
        "base_url": "",
    },
}

_STATE: Dict[str, str] = {
    "ai_backend": str(get_config("ai_backend.type", "ollama")),
    "selected_model": "",
}

_LOCAL_MODEL_CACHE: Dict[Tuple[str, str], Dict[str, Any]] = {}


def provider_choices() -> List[Dict[str, str]]:
    return [{"value": key, "label": value["label"]} for key, value in PROVIDER_PRESETS.items()]


def provider_section(backend: str) -> str:
    preset = PROVIDER_PRESETS.get(backend or "", PROVIDER_PRESETS["ollama"])
    return preset["section"]


def default_model_for_backend(backend: str) -> str:
    preset = PROVIDER_PRESETS.get(backend or "", PROVIDER_PRESETS["ollama"])
    return str(get_config(f"{preset['section']}.{preset['model_key']}", preset["default_model"]))


def get_backend_runtime_config(backend: str) -> Dict[str, str]:
    preset = PROVIDER_PRESETS.get(backend or "", PROVIDER_PRESETS["ollama"])
    section = preset["section"]
    return {
        "backend": backend,
        "label": preset["label"],
        "api_key": str(get_config(f"{section}.api_key", "")),
        "base_url": str(
            get_config(f"{section}.base_url", get_config(f"{section}.api_base", preset.get("base_url", "")))
        ).rstrip("/"),
        "model": str(get_config(f"{section}.{preset['model_key']}", preset["default_model"])),
    }


def save_backend_runtime_config(backend: str, api_key: str = "", base_url: str = "", model: str = "") -> Dict[str, str]:
    if backend not in PROVIDER_PRESETS:
        raise ValueError(f"未知后端: {backend}")
    preset = PROVIDER_PRESETS[backend]
    section = preset["section"]
    if backend == "local_adapter":
        if model is not None:
            set_config(f"{section}.{preset['model_key']}", model.strip())
        return get_backend_runtime_config(backend)
    if api_key is not None:
        set_config(f"{section}.api_key", api_key.strip())
    if base_url is not None:
        set_config(f"{section}.base_url", base_url.strip() or preset.get("base_url", ""))
    if model is not None and model.strip():
        set_config(f"{section}.{preset['model_key']}", model.strip())
    return get_backend_runtime_config(backend)


def list_ollama_models() -> List[str]:
    try:
        ollama_exe = "ollama"
        default_path = r"C:\Users\Administrator\AppData\Local\Programs\Ollama\ollama.exe"
        if default_path and os.path.exists(default_path):
            ollama_exe = default_path

        result = subprocess.run(
            [ollama_exe, "list"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            models: List[str] = []
            for line in result.stdout.strip().splitlines()[1:]:
                parts = line.split()
                if parts:
                    models.append(parts[0])
            return sorted(set(models))
    except Exception as exc:
        console_error(f"获取 Ollama 模型列表失败: {exc}")

    try:
        host = str(get_config("ollama.base_url", get_config("ollama.url", "http://127.0.0.1:11434"))).rstrip("/")
        response = requests.get(f"{host}/api/tags", timeout=5)
        response.raise_for_status()
        models = [str(item.get("name", "")) for item in response.json().get("models", []) if item.get("name")]
        return sorted(set(models))
    except Exception:
        return []


def list_local_adapter_models() -> List[str]:
    rows = model_linker.list_llm_deployments()
    return [str(item.get("name", "")).strip() for item in rows if str(item.get("name", "")).strip()]


def configured_model_catalog() -> Dict[str, List[str]]:
    catalog = {"ollama": list_ollama_models()}
    if not catalog["ollama"]:
        raw_defaults = get_config("ollama.default_models", "llava:7b-v1.5-q4_K_M")
        catalog["ollama"] = [item.strip() for item in str(raw_defaults).split(",") if item.strip()]
    catalog["local_adapter"] = list_local_adapter_models()
    for backend in PROVIDER_PRESETS:
        if backend in {"ollama", "local_adapter"}:
            continue
        model = default_model_for_backend(backend)
        catalog[backend] = [model] if model else []
    return catalog


def set_ai_backend(backend: str, model: str | None = None) -> None:
    target = backend if backend in PROVIDER_PRESETS else "ollama"
    _STATE["ai_backend"] = target
    if model is not None:
        _STATE["selected_model"] = model


def _active_model(model: str | None = None) -> str:
    if model and model.strip():
        return model.strip()
    selected = str(_STATE.get("selected_model") or "").strip()
    if selected:
        return selected
    return default_model_for_backend(_STATE.get("ai_backend", "ollama"))


def _timeout_seconds() -> float:
    try:
        return float(get_config("inference.timeout", 20))
    except Exception:
        return 20.0


def _encode_frame(frame: Any) -> str:
    ok, encoded = cv2.imencode(".jpg", frame)
    if not ok:
        raise RuntimeError("图像编码失败")
    return base64.b64encode(encoded.tobytes()).decode("utf-8")


def _openai_chat_completion(
    backend: str,
    prompt: str,
    model: str,
    frame: Any | None = None,
    max_tokens: int = 220,
) -> str:
    config = get_backend_runtime_config(backend)
    api_key = config.get("api_key", "").strip()
    base_url = config.get("base_url", "").rstrip("/")
    if not api_key:
        return f"{config['label']} 尚未配置 API Key。"
    if not base_url:
        return f"{config['label']} 尚未配置 Base URL。"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    content: List[Dict[str, Any]] = [{"type": "text", "text": prompt}]
    if frame is not None:
        try:
            content.insert(
                0,
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{_encode_frame(frame)}"},
                },
            )
        except Exception as exc:
            console_error(f"图像编码失败，已回退为纯文本请求: {exc}")
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": content}],
        "temperature": 0.3,
        "max_tokens": max_tokens,
    }
    response = requests.post(
        f"{base_url}/chat/completions",
        headers=headers,
        json=payload,
        timeout=_timeout_seconds(),
    )
    response.raise_for_status()
    data = response.json()
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("云端模型未返回有效结果")
    message = choices[0].get("message", {})
    result = str(message.get("content", "")).strip()
    return result or "云端模型未返回文本内容。"


def _ollama_generate(prompt: str, model: str, frame: Any | None = None) -> str:
    host = str(
        get_config("ollama.base_url", get_config("ollama.api_base", get_config("ollama.url", "http://127.0.0.1:11434")))
    ).rstrip("/")
    payload: Dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.3},
    }
    if frame is not None:
        payload["images"] = [_encode_frame(frame)]
    response = requests.post(f"{host}/api/generate", json=payload, timeout=_timeout_seconds())
    response.raise_for_status()
    result = str(response.json().get("response", "")).strip()
    return result or "本地模型未返回文本内容。"


def _load_local_adapter_runtime(base_model: str, adapter_path: str) -> Dict[str, Any]:
    cache_key = (str(base_model), str(adapter_path))
    cached = _LOCAL_MODEL_CACHE.get(cache_key)
    if cached is not None:
        return cached

    try:
        import torch
        from peft import PeftModel
        from transformers import AutoModelForCausalLM, AutoTokenizer
    except Exception as exc:  # pragma: no cover - optional dependency
        raise RuntimeError(f"未安装本地微调模型推理依赖: {exc}") from exc

    model_source = str(base_model).strip()
    adapter_source = str(adapter_path).strip()
    if not model_source:
        raise RuntimeError("本地微调模型缺少底座模型路径。")
    if not adapter_source or not Path(adapter_source).exists():
        raise RuntimeError("本地微调模型适配器目录不存在。")

    tokenizer_source = adapter_source if Path(adapter_source, "tokenizer_config.json").exists() else model_source
    tokenizer = AutoTokenizer.from_pretrained(tokenizer_source, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    torch_dtype = torch.float16 if torch.cuda.is_available() else torch.float32
    base = AutoModelForCausalLM.from_pretrained(model_source, trust_remote_code=True, torch_dtype=torch_dtype)
    model = PeftModel.from_pretrained(base, adapter_source)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = model.to(device)
    model.eval()

    cached = {"tokenizer": tokenizer, "model": model, "device": device, "torch": torch}
    _LOCAL_MODEL_CACHE[cache_key] = cached
    return cached


def _local_adapter_generate(prompt: str, model: str, frame: Any | None = None) -> str:
    deployment = model_linker.resolve_llm_deployment(model)
    if deployment is None:
        return "当前未找到可用的本地微调模型，请先在训练工作台完成 LLM 微调。"

    prompt_text = str(prompt or "").strip()
    if frame is not None:
        prompt_text = (
            "你正在使用本地文本微调模型。当前不会直接解析图像像素，请基于问题文本、知识库上下文和已有语义线索作答。\n\n"
            + prompt_text
        )

    runtime = _load_local_adapter_runtime(str(deployment.get("base_model", "")), str(deployment.get("adapter_path", "")))
    tokenizer = runtime["tokenizer"]
    model_obj = runtime["model"]
    device = runtime["device"]
    torch = runtime["torch"]

    max_new_tokens = int(get_config("local_llm.generation_max_new_tokens", 192) or 192)
    temperature = float(get_config("local_llm.temperature", 0.3) or 0.3)
    top_p = float(get_config("local_llm.top_p", 0.9) or 0.9)

    encoded = tokenizer(prompt_text, return_tensors="pt", truncation=True, max_length=1024)
    encoded = {key: value.to(device) for key, value in encoded.items()}
    with torch.inference_mode():
        generated = model_obj.generate(
            **encoded,
            max_new_tokens=max(32, max_new_tokens),
            do_sample=temperature > 0,
            temperature=max(0.0, temperature),
            top_p=max(0.1, top_p),
            pad_token_id=tokenizer.pad_token_id,
            eos_token_id=tokenizer.eos_token_id,
        )
    output_ids = generated[0][encoded["input_ids"].shape[-1] :]
    text = tokenizer.decode(output_ids, skip_special_tokens=True).strip()
    if not text:
        return "本地微调模型未返回有效文本。"
    return text


def analyze_image(frame, model: str, prompt: str = "请精准描述画面内容，控制在20字以内，仅返回描述文本。") -> str:
    backend = _STATE.get("ai_backend", "ollama")
    active_model = _active_model(model)
    try:
        if backend == "ollama":
            result = _ollama_generate(prompt, active_model, frame=frame)
        elif backend == "local_adapter":
            result = _local_adapter_generate(prompt, active_model, frame=frame)
        else:
            result = _openai_chat_completion(backend, prompt, active_model, frame=frame, max_tokens=180)
        console_info(f"{backend} 识别结果: {result}")
        return result
    except Exception as exc:
        console_error(f"{backend} 图像分析失败: {exc}")
        return "图像分析失败"


def ask_assistant_with_rag(frame, question: str, rag_context: str, model_name: str) -> str:
    prompt = (
        "你是一名实验室监控与安全辅助专家。请结合当前问题、知识库背景和可见画面，"
        "用简洁、专业的中文回答，控制在 80 字以内。\n\n"
        f"【知识库背景】\n{rag_context or '暂无相关背景知识。'}\n\n"
        f"【用户问题】\n{question}\n"
    )
    backend = _STATE.get("ai_backend", "ollama")
    active_model = _active_model(model_name)
    try:
        if backend == "ollama":
            return _ollama_generate(prompt, active_model, frame=frame)
        if backend == "local_adapter":
            return _local_adapter_generate(prompt, active_model, frame=frame)
        return _openai_chat_completion(backend, prompt, active_model, frame=frame, max_tokens=220)
    except Exception as exc:
        console_error(f"{backend} 问答失败: {exc}")
        return f"模型回答失败: {str(exc)[:60]}"
