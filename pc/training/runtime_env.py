from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List

from pc.app_identity import external_app_root, is_frozen_runtime, project_root
from pc.core.subprocess_utils import run_hidden


_COMMON_PYTHON_CANDIDATES = [
    Path(r"C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe"),
    Path(r"C:\Python311\python.exe"),
    Path(r"C:\Program Files\Python311\python.exe"),
    Path(r"C:\Program Files\Python312\python.exe"),
]


def support_root() -> Path:
    if is_frozen_runtime():
        return Path(external_app_root())
    candidate = Path(project_root()) / "pc" / "APP"
    return candidate if candidate.exists() else Path(project_root())


def training_python_root() -> Path:
    return support_root() / "python_runtime"


def training_worker_script_path() -> Path:
    if is_frozen_runtime():
        return support_root() / "training_runtime" / "training_worker.py"
    return Path(project_root()) / "pc" / "training" / "training_worker.py"


def install_target_for_training_packages() -> Path | None:
    if is_frozen_runtime():
        return support_root()
    return None


def resolve_training_python_executable() -> Path | None:
    if not is_frozen_runtime():
        return Path(sys.executable).resolve()

    bundled = training_python_root() / "python.exe"
    if bundled.exists():
        return bundled

    located = shutil.which("python")
    if located:
        return Path(located).resolve()

    for candidate in _COMMON_PYTHON_CANDIDATES:
        if candidate.exists():
            return candidate.resolve()
    return None


def describe_training_python() -> Dict[str, Any]:
    python_exe = resolve_training_python_executable()
    runtime_root = training_python_root()
    if python_exe is None:
        return {
            "available": False,
            "kind": "missing",
            "path": "",
            "reason": "未找到训练运行时 Python。请运行桌面构建脚本，或补齐 APP/python_runtime。",
        }

    kind = "current"
    if is_frozen_runtime() and runtime_root in python_exe.parents:
        kind = "bundled"
    elif is_frozen_runtime():
        kind = "system"

    return {
        "available": True,
        "kind": kind,
        "path": str(python_exe),
        "reason": "",
    }


def build_training_python_env(python_exe: Path | None = None, extra_pythonpath: Iterable[str] | None = None) -> Dict[str, str]:
    env = os.environ.copy()
    python_exe = python_exe or resolve_training_python_executable()
    path_parts: List[str] = []
    project = Path(project_root())
    support = support_root()

    if not is_frozen_runtime():
        path_parts.append(str(project))
        if support != project:
            path_parts.append(str(support))
    else:
        path_parts.append(str(support))

    if extra_pythonpath:
        for item in extra_pythonpath:
            value = str(item).strip()
            if value:
                path_parts.append(value)

    existing_pythonpath = str(env.get("PYTHONPATH") or "").strip()
    if existing_pythonpath:
        path_parts.append(existing_pythonpath)
    env["PYTHONPATH"] = os.pathsep.join(path_parts)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"

    runtime_root = training_python_root()
    if python_exe is not None and runtime_root.exists() and runtime_root in Path(python_exe).resolve().parents:
        env["PYTHONHOME"] = str(runtime_root)

    return env


def _decode_output(payload: bytes) -> str:
    for encoding in ("utf-8", "gbk", "cp936"):
        try:
            return payload.decode(encoding)
        except Exception:
            continue
    return payload.decode("utf-8", errors="ignore")


def probe_modules_with_training_python(module_names: Iterable[str]) -> Dict[str, Any]:
    info = describe_training_python()
    module_list = [str(item).strip() for item in module_names if str(item).strip()]
    if not info["available"]:
        return {
            "ok": False,
            "available": False,
            "python": "",
            "results": {name: False for name in module_list},
            "logs": [f"[ERROR] {info['reason']}"] if info.get("reason") else [],
        }

    python_exe = Path(info["path"])
    command = [
        str(python_exe),
        "-c",
        (
            "import importlib.util, json, sys; "
            "print(json.dumps({name: importlib.util.find_spec(name) is not None for name in sys.argv[1:]}, ensure_ascii=False))"
        ),
        *module_list,
    ]
    proc = run_hidden(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=build_training_python_env(python_exe),
        timeout=30,
    )
    output = _decode_output(proc.stdout).strip()
    results: Dict[str, bool] = {}
    if proc.returncode == 0:
        try:
            loaded = json.loads(output.splitlines()[-1]) if output else {}
            if isinstance(loaded, dict):
                results = {str(key): bool(value) for key, value in loaded.items()}
        except Exception:
            results = {}
    return {
        "ok": proc.returncode == 0 and bool(results),
        "available": True,
        "python": str(python_exe),
        "results": results,
        "logs": [f"[INFO] 训练运行时解释器: {python_exe}"] + ([f"[INFO] {line}" for line in output.splitlines()[:-1]] if output else []),
    }
