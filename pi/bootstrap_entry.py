#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""树莓派边缘端轻量启动引导器。"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, Iterable, List

try:
    from .tools.runtime_installer import (
        build_status_payload,
        is_install_completed,
        is_install_running,
        trigger_background_install,
    )
except ImportError:
    from tools.runtime_installer import (
        build_status_payload,
        is_install_completed,
        is_install_running,
        trigger_background_install,
    )


PI_BOOTSTRAP_DEPENDENCY_MAP: Dict[str, str] = {
    "numpy": "numpy",
    "cv2": "opencv-python-headless",
    "websockets": "websockets",
    "torch": "torch",
    "torchvision": "torchvision",
    "ultralytics": "ultralytics",
    "pyaudio": "pyaudio",
    "vosk": "vosk",
    "pyttsx3": "pyttsx3",
}


def _script_dir() -> Path:
    return Path(__file__).resolve().parent


def _offline_dir() -> Path:
    return _script_dir() / "offline"


def _pi_cli_path() -> Path:
    app_candidate = _script_dir() / "APP" / "pi_cli.py"
    if app_candidate.exists():
        return app_candidate
    return _script_dir() / "pi_cli.py"


def _run(command: List[str], timeout: int = 1800) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="ignore",
        timeout=timeout,
        cwd=str(_script_dir()),
    )


def _ensure_pip() -> None:
    probe = _run([sys.executable, "-m", "pip", "--version"], timeout=120)
    if probe.returncode == 0:
        return
    repair = _run([sys.executable, "-m", "ensurepip", "--upgrade"], timeout=300)
    if repair.returncode != 0:
        summary = "；".join([line.strip() for line in repair.stdout.splitlines() if line.strip()][-3:]) or "无可用日志"
        raise RuntimeError(f"Pi 启动前修复 pip 失败：{summary}")


def _probe_missing_modules(module_names: Iterable[str]) -> List[str]:
    names = [name for name in module_names if name]
    if not names:
        return []
    command = [
        sys.executable,
        "-c",
        "import importlib.util, json, sys; "
        "print(json.dumps({name: importlib.util.find_spec(name) is not None for name in sys.argv[1:]}, ensure_ascii=False))",
        *names,
    ]
    result = _run(command, timeout=120)
    if result.returncode != 0 or not result.stdout.strip():
        return names
    try:
        parsed = json.loads(result.stdout.strip().splitlines()[-1])
    except Exception:
        return names
    return [name for name, ok in parsed.items() if not ok]


def _runtime_ready() -> bool:
    if not is_install_completed():
        return False
    missing_modules = _probe_missing_modules(PI_BOOTSTRAP_DEPENDENCY_MAP.keys())
    return not missing_modules


def _print_install_status(prefix: str) -> None:
    status = build_status_payload()
    print(prefix)
    print(json.dumps(status, ensure_ascii=False, indent=2))


def _maybe_schedule_runtime_install() -> int:
    if is_install_running():
        _print_install_status("[INFO] Pi 运行时安装正在后台执行，无需重复触发。")
        return 0
    schedule = trigger_background_install()
    print("[INFO] Pi 运行时安装未完成，已切换为后台自治安装。")
    print(json.dumps(schedule, ensure_ascii=False, indent=2))
    return 0


def _launch_main(args: List[str]) -> int:
    command = [sys.executable, str(_pi_cli_path()), *args]
    process = subprocess.run(command, cwd=str(_script_dir()))
    return int(process.returncode)


def main(argv: List[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    if not args:
        args = ["start"]
    passthrough_commands = {"status", "config", "version", "install-runtime", "install-status", "install-log"}
    if args[0] not in passthrough_commands and not _runtime_ready():
        return _maybe_schedule_runtime_install()
    return _launch_main(args)


if __name__ == "__main__":
    raise SystemExit(main())
