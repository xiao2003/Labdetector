from __future__ import annotations

import hashlib
import json
import shutil
import threading
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from pc.app_identity import resource_path
from pc.core.config import get_config
from pc.core.runtime_assets import orchestrator_download_dir, orchestrator_model_dir, orchestrator_state_path
from pc.core.subprocess_utils import run_hidden


STATE_NOT_INSTALLED = "not_installed"
STATE_DOWNLOADING = "downloading"
STATE_DOWNLOAD_FAILED = "download_failed"
STATE_WARMING_UP = "warming_up"
STATE_READY = "ready"
VALID_STATES = {
    STATE_NOT_INSTALLED,
    STATE_DOWNLOADING,
    STATE_DOWNLOAD_FAILED,
    STATE_WARMING_UP,
    STATE_READY,
}
_PREPARE_LOCK = threading.Lock()


@dataclass(frozen=True)
class OrchestratorRuntimeStatus:
    """固定管家层运行时状态。"""

    enabled: bool
    runtime_path: str
    model_path: str
    runtime_exists: bool
    model_exists: bool
    ready: bool
    reason: str
    status: str
    planner_backend: str


class OrchestratorRuntimeError(RuntimeError):
    """固定管家层运行时错误。"""


def _now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _default_state() -> Dict[str, Any]:
    return {
        "status": STATE_NOT_INSTALLED,
        "planner_backend": "deterministic",
        "reason": "固定管家层模型尚未安装",
        "error": "",
        "runtime_path": "",
        "model_path": "",
        "runtime_version": "",
        "model_name": "",
        "updated_at": _now_text(),
    }


def _resolve_project_resource(relative_key: str, default_relative: str) -> Path:
    raw_value = str(get_config(relative_key, default_relative) or default_relative).strip()
    normalized = raw_value.replace("\\", "/")
    if not normalized:
        return resource_path(default_relative)
    direct = Path(normalized)
    if direct.is_absolute():
        return direct
    return resource_path(normalized)


def asset_manifest_path() -> Path:
    return _resolve_project_resource(
        "orchestrator.asset_manifest_relpath",
        "pc/models/orchestrator/orchestrator_assets.json",
    )


def load_asset_manifest() -> Dict[str, Any]:
    manifest = json.loads(asset_manifest_path().read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise OrchestratorRuntimeError("固定管家层资产清单格式错误。")
    return manifest


def runtime_binary_path() -> Path:
    return _resolve_project_resource(
        "orchestrator.runtime_relpath",
        "pc/runtime/llm_orchestrator/llama-cli.exe",
    )


def model_binary_path() -> Path:
    manifest = load_asset_manifest()
    filename = str(manifest.get("model", {}).get("filename") or "").strip()
    if not filename:
        raise OrchestratorRuntimeError("固定管家层模型清单缺少 filename。")
    return orchestrator_model_dir() / filename


def read_runtime_state() -> Dict[str, Any]:
    path = orchestrator_state_path()
    if not path.exists():
        return _default_state()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return _default_state()
    if not isinstance(payload, dict):
        return _default_state()
    merged = _default_state()
    merged.update(payload)
    status = str(merged.get("status") or STATE_NOT_INSTALLED).strip()
    if status not in VALID_STATES:
        merged["status"] = STATE_NOT_INSTALLED
    return merged


def _write_runtime_state(
    status: str,
    *,
    reason: str,
    error: str = "",
    planner_backend: str = "deterministic",
) -> Dict[str, Any]:
    manifest = load_asset_manifest()
    payload = {
        "status": status,
        "planner_backend": planner_backend,
        "reason": reason,
        "error": error,
        "runtime_path": str(runtime_binary_path()),
        "model_path": str(model_binary_path()),
        "runtime_version": str(manifest.get("runtime", {}).get("version") or ""),
        "model_name": str(manifest.get("model", {}).get("filename") or ""),
        "updated_at": _now_text(),
    }
    path = orchestrator_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def _build_runtime_cache_root() -> Path:
    manifest = load_asset_manifest()
    version = str(manifest.get("runtime", {}).get("version") or "unknown").strip() or "unknown"
    root = asset_manifest_path().resolve().parents[3] / ".build" / "orchestrator_runtime" / version
    root.mkdir(parents=True, exist_ok=True)
    return root


def _log(log_callback: Optional[Callable[[str], None]], message: str) -> None:
    if log_callback is not None:
        log_callback(message)


def _sha256_of_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download_file(
    *,
    url: str,
    target_path: Path,
    expected_sha256: str,
    expected_size: int,
    log_callback: Optional[Callable[[str], None]] = None,
) -> Path:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = target_path.with_suffix(target_path.suffix + ".part")
    if temp_path.exists():
        temp_path.unlink()
    _log(log_callback, f"开始下载固定资产: {url}")
    request = urllib.request.Request(url, headers={"User-Agent": "NeuroLabHub/1.0.0"})
    downloaded = 0
    with urllib.request.urlopen(request, timeout=120) as response, temp_path.open("wb") as handle:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            handle.write(chunk)
            downloaded += len(chunk)
    if expected_size and downloaded != int(expected_size):
        raise OrchestratorRuntimeError(f"固定资产大小校验失败: 期望 {expected_size}，实际 {downloaded}")
    actual_sha256 = _sha256_of_file(temp_path)
    if expected_sha256 and actual_sha256.lower() != str(expected_sha256).lower():
        raise OrchestratorRuntimeError("固定资产 SHA256 校验失败。")
    temp_path.replace(target_path)
    return target_path


def _prepare_runtime_cache(log_callback: Optional[Callable[[str], None]] = None) -> Path:
    manifest = load_asset_manifest()
    runtime_meta = dict(manifest.get("runtime") or {})
    entrypoint = str(runtime_meta.get("entrypoint") or "llama-cli.exe").strip()
    cache_root = _build_runtime_cache_root()
    entrypoint_path = cache_root / entrypoint
    if entrypoint_path.exists():
        return cache_root

    zip_name = str(runtime_meta.get("asset_name") or "").strip()
    download_url = str(runtime_meta.get("download_url") or "").strip()
    sha256 = str(runtime_meta.get("sha256") or "").strip()
    size = int(runtime_meta.get("size") or 0)
    if not zip_name or not download_url:
        raise OrchestratorRuntimeError("固定管家层 runtime 清单不完整。")

    archive_path = cache_root / zip_name
    if not archive_path.exists():
        _download_file(
            url=download_url,
            target_path=archive_path,
            expected_sha256=sha256,
            expected_size=size,
            log_callback=log_callback,
        )

    extract_root = cache_root / "extract"
    if extract_root.exists():
        shutil.rmtree(extract_root)
    with zipfile.ZipFile(archive_path, "r") as archive:
        archive.extractall(extract_root)

    copied = 0
    for item in extract_root.iterdir():
        if item.is_file() and (item.name.lower().endswith(".dll") or item.name.lower() == entrypoint.lower()):
            shutil.copy2(item, cache_root / item.name)
            copied += 1
    if not entrypoint_path.exists():
        raise OrchestratorRuntimeError("固定管家层 runtime 解压后缺少 llama-cli.exe。")
    if copied <= 1:
        raise OrchestratorRuntimeError("固定管家层 runtime 解压结果异常，缺少必要依赖文件。")
    return cache_root


def materialize_runtime_bundle(
    destination_dir: Path,
    *,
    log_callback: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    cache_root = _prepare_runtime_cache(log_callback=log_callback)
    destination_dir.mkdir(parents=True, exist_ok=True)
    copied_files: list[str] = []
    for item in cache_root.iterdir():
        if not item.is_file():
            continue
        if not (item.name.lower().endswith(".dll") or item.name.lower() == "llama-cli.exe"):
            continue
        target = destination_dir / item.name
        shutil.copy2(item, target)
        copied_files.append(item.name)
    if "llama-cli.exe" not in copied_files:
        raise OrchestratorRuntimeError("固定管家层 runtime 复制失败：未包含 llama-cli.exe。")
    return {
        "runtime_dir": str(destination_dir),
        "copied_files": copied_files,
    }


def _invoke_runtime(prompt: str, *, timeout_seconds: Optional[float] = None) -> str:
    runtime_path = runtime_binary_path()
    model_path = model_binary_path()
    command = [
        str(runtime_path),
        "-m",
        str(model_path),
        "-p",
        str(prompt or ""),
        "-c",
        str(int(get_config("orchestrator.num_ctx", 2048) or 2048)),
        "-n",
        str(int(get_config("orchestrator.num_predict", 256) or 256)),
        "--temp",
        str(float(get_config("orchestrator.temperature", 0.1) or 0.1)),
        "--top-p",
        str(float(get_config("orchestrator.top_p", 0.8) or 0.8)),
        "--top-k",
        str(int(get_config("orchestrator.top_k", 20) or 20)),
        "--no-display-prompt",
    ]
    completed = run_hidden(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=float(timeout_seconds or get_config("orchestrator.timeout_seconds", 8) or 8),
        check=False,
    )
    if completed.returncode != 0:
        stderr = str(completed.stderr or completed.stdout or "").strip()
        raise OrchestratorRuntimeError(f"固定管家层推理失败: {stderr or '未知错误'}")
    return str(completed.stdout or "")


def _extract_first_json_object(raw_text: str) -> Dict[str, Any]:
    text = str(raw_text or "").strip()
    if not text:
        raise OrchestratorRuntimeError("固定管家层模型未返回内容。")
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise OrchestratorRuntimeError("固定管家层模型未返回合法 JSON。")
    try:
        payload = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise OrchestratorRuntimeError(f"固定管家层 JSON 解析失败: {exc}") from exc
    if not isinstance(payload, dict):
        raise OrchestratorRuntimeError("固定管家层输出不是 JSON 对象。")
    return payload


def _download_model_if_needed(log_callback: Optional[Callable[[str], None]] = None) -> Path:
    manifest = load_asset_manifest()
    model_meta = dict(manifest.get("model") or {})
    target_path = model_binary_path()
    expected_size = int(model_meta.get("size") or 0)
    expected_sha256 = str(model_meta.get("sha256") or "").strip()
    if target_path.exists():
        actual_size = target_path.stat().st_size
        if actual_size == expected_size and _sha256_of_file(target_path).lower() == expected_sha256.lower():
            return target_path
    download_dir = orchestrator_download_dir()
    archive_path = download_dir / str(model_meta.get("filename") or "model.gguf")
    _download_file(
        url=str(model_meta.get("download_url") or "").strip(),
        target_path=archive_path,
        expected_sha256=expected_sha256,
        expected_size=expected_size,
        log_callback=log_callback,
    )
    target_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(archive_path, target_path)
    return target_path


def warm_up_orchestrator_runtime(log_callback: Optional[Callable[[str], None]] = None) -> None:
    _log(log_callback, "固定管家层模型开始后台预热。")
    raw_output = _invoke_runtime('请只输出 JSON：{"ready":true,"intent":"warmup"}', timeout_seconds=20)
    payload = _extract_first_json_object(raw_output)
    if payload.get("ready") is not True:
        raise OrchestratorRuntimeError("固定管家层模型预热未返回 ready=true。")


def prepare_orchestrator_assets(log_callback: Optional[Callable[[str], None]] = None) -> Dict[str, Any]:
    with _PREPARE_LOCK:
        enabled = bool(get_config("orchestrator.enabled", True))
        if not enabled:
            return _write_runtime_state(
                STATE_NOT_INSTALLED,
                reason="固定管家层模型已禁用",
                planner_backend="deterministic",
            )

        runtime_path = runtime_binary_path()
        if not runtime_path.exists():
            return _write_runtime_state(
                STATE_NOT_INSTALLED,
                reason="固定管家层 runtime 尚未随安装包就位",
                planner_backend="deterministic",
            )

        try:
            if not model_binary_path().exists():
                _write_runtime_state(
                    STATE_DOWNLOADING,
                    reason="固定管家层模型正在后台下载",
                    planner_backend="deterministic",
                )
                _download_model_if_needed(log_callback=log_callback)
            _write_runtime_state(
                STATE_WARMING_UP,
                reason="固定管家层模型正在后台预热",
                planner_backend="deterministic",
            )
            warm_up_orchestrator_runtime(log_callback=log_callback)
            return _write_runtime_state(
                STATE_READY,
                reason="固定管家层模型已就绪",
                planner_backend="embedded_model",
            )
        except Exception as exc:
            return _write_runtime_state(
                STATE_DOWNLOAD_FAILED,
                reason="固定管家层模型后台准备失败",
                error=str(exc),
                planner_backend="deterministic",
            )


def get_runtime_status() -> OrchestratorRuntimeStatus:
    enabled = bool(get_config("orchestrator.enabled", True))
    runtime_path = runtime_binary_path()
    model_path = model_binary_path()
    runtime_exists = runtime_path.exists()
    model_exists = model_path.exists()
    state = read_runtime_state()
    status_name = str(state.get("status") or STATE_NOT_INSTALLED).strip()
    planner_backend = str(state.get("planner_backend") or "deterministic").strip() or "deterministic"
    ready = bool(enabled and runtime_exists and model_exists and status_name == STATE_READY)

    if not enabled:
        reason = "固定管家层模型已禁用"
        planner_backend = "deterministic"
        status_name = STATE_NOT_INSTALLED
    elif not runtime_exists:
        reason = "缺少内置 llama.cpp 运行时"
        planner_backend = "deterministic"
        status_name = STATE_NOT_INSTALLED
    elif not model_exists and status_name == STATE_DOWNLOADING:
        reason = "固定管家层模型正在后台下载"
    elif status_name == STATE_WARMING_UP:
        reason = "固定管家层模型正在后台预热"
    elif status_name == STATE_DOWNLOAD_FAILED:
        error = str(state.get("error") or "").strip()
        reason = error or "固定管家层模型后台准备失败"
    elif ready:
        reason = "固定管家层运行时已就绪"
    elif model_exists:
        reason = "固定管家层模型已下载，等待后台预热"
        planner_backend = "deterministic"
    else:
        reason = "固定管家层模型尚未下载"
        planner_backend = "deterministic"

    return OrchestratorRuntimeStatus(
        enabled=enabled,
        runtime_path=str(runtime_path),
        model_path=str(model_path),
        runtime_exists=runtime_exists,
        model_exists=model_exists,
        ready=ready,
        reason=reason,
        status=status_name,
        planner_backend=planner_backend,
    )


def invoke_orchestrator_model(prompt: str) -> Dict[str, Any]:
    status = get_runtime_status()
    if not status.ready:
        raise OrchestratorRuntimeError(status.reason)
    return _extract_first_json_object(_invoke_runtime(prompt))
