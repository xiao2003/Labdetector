#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Pi 运行时自治安装器。"""

from __future__ import annotations

import importlib.util
import json
import os
import signal
import subprocess
import sys
import time
import venv
from pathlib import Path
from typing import Dict, Iterable, List

CURRENT_FILE = Path(__file__).resolve()
PI_ROOT = CURRENT_FILE.parents[1]
if str(PI_ROOT) not in sys.path:
    sys.path.insert(0, str(PI_ROOT))

try:
    from ..config import set_pi_config
    from ..tools.model_downloader import check_and_download_vosk
except ImportError:
    from config import set_pi_config
    from tools.model_downloader import check_and_download_vosk

RUNTIME_STATE_DIR = PI_ROOT / "runtime_state"
INSTALL_STATE_PATH = RUNTIME_STATE_DIR / "install_state.json"
INSTALL_LOG_PATH = RUNTIME_STATE_DIR / "install.log"
INSTALL_PID_PATH = RUNTIME_STATE_DIR / "install.pid"
VENV_DIR = PI_ROOT / ".venv"
VENV_PYTHON = VENV_DIR / "bin" / "python3"

SYSTEM_PACKAGES = [
    "python3-torch",
    "python3-torchvision",
    "python3-pyaudio",
]

PYTHON_MODULE_PACKAGE_MAP: Dict[str, str] = {
    "cv2": "opencv-python-headless",
    "websockets": "websockets",
    "vosk": "vosk",
    "ultralytics": "ultralytics",
    "cpuinfo": "py-cpuinfo",
    "pyttsx3": "pyttsx3",
}

SUCCESS_STATUS = "success"
RUNNING_STATUS = "running"
FAILED_STATUS = "failed"


def _now_text() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _ensure_state_dir() -> None:
    RUNTIME_STATE_DIR.mkdir(parents=True, exist_ok=True)


def _append_log(message: str) -> None:
    _ensure_state_dir()
    with INSTALL_LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(f"[{_now_text()}] {message}\n")


def _read_json(path: Path) -> Dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def read_install_state() -> Dict:
    return _read_json(INSTALL_STATE_PATH)


def _write_install_state(payload: Dict) -> None:
    _ensure_state_dir()
    payload["updated_at"] = _now_text()
    INSTALL_STATE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_pid() -> int | None:
    if not INSTALL_PID_PATH.exists():
        return None
    try:
        return int(INSTALL_PID_PATH.read_text(encoding="utf-8").strip())
    except Exception:
        return None


def _write_pid(pid: int) -> None:
    _ensure_state_dir()
    INSTALL_PID_PATH.write_text(str(pid), encoding="utf-8")


def _clear_pid() -> None:
    try:
        INSTALL_PID_PATH.unlink()
    except FileNotFoundError:
        pass


def _pid_alive(pid: int | None) -> bool:
    if not pid or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def is_install_running() -> bool:
    return _pid_alive(_read_pid())


def is_install_completed() -> bool:
    state = read_install_state()
    return state.get("status") == SUCCESS_STATUS


def _run(command: List[str], timeout: int = 7200, env: Dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    return subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="ignore",
        timeout=timeout,
        cwd=str(PI_ROOT),
        env=merged_env,
    )


def _sudo_prefix() -> List[str]:
    return [] if os.geteuid() == 0 else ["sudo"]


def _missing_system_packages() -> List[str]:
    missing: List[str] = []
    for package in SYSTEM_PACKAGES:
        result = _run(["dpkg-query", "-W", "-f=${Status}", package], timeout=60)
        if result.returncode != 0 or "install ok installed" not in result.stdout:
            missing.append(package)
    return missing


def _probe_missing_modules(module_names: Iterable[str], python_executable: str) -> List[str]:
    names = [name for name in module_names if name]
    if not names:
        return []
    result = _run(
        [
            python_executable,
            "-c",
            "import importlib.util, json, sys; "
            "print(json.dumps({name: importlib.util.find_spec(name) is not None for name in sys.argv[1:]}, ensure_ascii=False))",
            *names,
        ],
        timeout=120,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return names
    try:
        parsed = json.loads(result.stdout.strip().splitlines()[-1])
    except Exception:
        return names
    return [name for name, ok in parsed.items() if not ok]


def _ensure_venv() -> None:
    _append_log(f"[INFO] 检查项目虚拟环境: {VENV_DIR}")
    builder = venv.EnvBuilder(system_site_packages=True, with_pip=True, clear=False, upgrade=True)
    builder.create(str(VENV_DIR))
    _run([str(VENV_PYTHON), "-m", "ensurepip", "--upgrade"], timeout=600)


def _install_system_packages(packages: List[str]) -> None:
    if not packages:
        _append_log("[INFO] 系统包已满足，无需安装。")
        return
    _append_log(f"[INFO] 开始安装系统包: {', '.join(packages)}")
    result = _run(
        [*_sudo_prefix(), "apt-get", "update"],
        timeout=7200,
        env={"DEBIAN_FRONTEND": "noninteractive"},
    )
    if result.returncode != 0:
        raise RuntimeError(f"apt update 失败: {result.stdout.strip().splitlines()[-1] if result.stdout.strip() else '无日志'}")
    result = _run(
        [*_sudo_prefix(), "apt-get", "install", "-y", "--no-install-recommends", *packages],
        timeout=14400,
        env={"DEBIAN_FRONTEND": "noninteractive"},
    )
    if result.returncode != 0:
        lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        raise RuntimeError(f"系统包安装失败: {'；'.join(lines[-8:]) if lines else '无日志'}")


def _missing_python_packages() -> List[str]:
    python_executable = str(VENV_PYTHON if VENV_PYTHON.exists() else Path(sys.executable))
    missing_modules = _probe_missing_modules(PYTHON_MODULE_PACKAGE_MAP.keys(), python_executable)
    return [PYTHON_MODULE_PACKAGE_MAP[name] for name in missing_modules]


def _install_python_packages(packages: List[str]) -> None:
    if not packages:
        _append_log("[INFO] Python 包已满足，无需安装。")
        return
    _append_log(f"[INFO] 开始安装 Python 包: {', '.join(packages)}")
    result = _run(
        [
            str(VENV_PYTHON),
            "-m",
            "pip",
            "install",
            "--upgrade",
            "--disable-pip-version-check",
            *packages,
        ],
        timeout=14400,
    )
    if result.returncode != 0:
        lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        raise RuntimeError(f"Python 包安装失败: {'；'.join(lines[-8:]) if lines else '无日志'}")


def _ensure_vosk_model() -> None:
    model_dir = PI_ROOT / "voice" / "model"
    if (model_dir / "am").exists():
        _append_log("[INFO] Vosk 模型已就位。")
        return
    _append_log("[INFO] 开始准备 Vosk 模型。")
    if not check_and_download_vosk(str(model_dir), allow_download=True):
        raise RuntimeError("Vosk 模型准备失败")


def _apply_pi5_defaults() -> None:
    defaults = {
        "detector.weights_path": "yolov8n.pt",
        "detector.conf": "0.4",
        "detector.imgsz": "640",
        "voice.model_path": "voice/model",
        "network.ws_port": "8001",
        "self_check.auto_install_dependencies": "False",
    }
    for key, value in defaults.items():
        set_pi_config(key, value)
    _append_log("[INFO] 已写入 Pi 5 稳定档默认配置。")


def _verify_runtime() -> Dict[str, List[str] | bool]:
    missing_system = _missing_system_packages()
    missing_python = _missing_python_packages()
    model_ready = (PI_ROOT / "voice" / "model" / "am").exists()
    return {
        "missing_system_packages": missing_system,
        "missing_python_packages": missing_python,
        "model_ready": model_ready,
    }


def _set_running_state(stage: str, **extra: object) -> None:
    payload = read_install_state()
    payload.update(
        {
            "status": RUNNING_STATUS,
            "stage": stage,
            "started_at": payload.get("started_at") or _now_text(),
        }
    )
    payload.update(extra)
    _write_install_state(payload)


def _set_failed_state(stage: str, error: str, **extra: object) -> None:
    payload = read_install_state()
    payload.update({"status": FAILED_STATUS, "stage": stage, "error": error})
    payload.update(extra)
    _write_install_state(payload)
    _append_log(f"[ERROR] {stage} 阶段失败: {error}")


def _set_success_state(runtime_snapshot: Dict[str, object]) -> None:
    payload = {
        "status": SUCCESS_STATUS,
        "stage": "verify",
        "error": "",
        "started_at": read_install_state().get("started_at") or _now_text(),
        **runtime_snapshot,
    }
    _write_install_state(payload)
    _append_log("[INFO] Pi 运行时安装完成。")


def run_install() -> int:
    _ensure_state_dir()
    _write_pid(os.getpid())
    try:
        initial_missing_system = _missing_system_packages()
        _set_running_state("apt", missing_system_packages=initial_missing_system, missing_python_packages=[])
        _install_system_packages(initial_missing_system)

        _set_running_state("venv", missing_system_packages=[], missing_python_packages=[])
        _ensure_venv()

        missing_python = _missing_python_packages()
        _set_running_state("pip", missing_system_packages=[], missing_python_packages=missing_python)
        _install_python_packages(missing_python)

        _set_running_state("model", missing_system_packages=[], missing_python_packages=[])
        _ensure_vosk_model()
        _apply_pi5_defaults()

        _set_running_state("verify", missing_system_packages=[], missing_python_packages=[])
        runtime_snapshot = _verify_runtime()
        if runtime_snapshot["missing_system_packages"] or runtime_snapshot["missing_python_packages"] or not runtime_snapshot["model_ready"]:
            raise RuntimeError("安装后校验仍存在缺口")
        _set_success_state(runtime_snapshot)
        return 0
    except Exception as exc:
        state = read_install_state()
        _set_failed_state(str(state.get("stage") or "unknown"), str(exc), **_verify_runtime())
        return 1
    finally:
        _clear_pid()


def trigger_background_install(force: bool = False) -> Dict[str, object]:
    _ensure_state_dir()
    if is_install_running():
        return {
            "scheduled": False,
            "already_running": True,
            "pid": _read_pid(),
            "state_path": str(INSTALL_STATE_PATH),
            "log_path": str(INSTALL_LOG_PATH),
        }
    if is_install_completed() and not force:
        return {
            "scheduled": False,
            "already_running": False,
            "completed": True,
            "pid": None,
            "state_path": str(INSTALL_STATE_PATH),
            "log_path": str(INSTALL_LOG_PATH),
        }

    _set_running_state("apt", missing_system_packages=_missing_system_packages(), missing_python_packages=[])
    with INSTALL_LOG_PATH.open("a", encoding="utf-8") as log_handle:
        process = subprocess.Popen(
            [sys.executable, str(CURRENT_FILE), "--run"],
            cwd=str(PI_ROOT),
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    _write_pid(process.pid)
    return {
        "scheduled": True,
        "already_running": False,
        "completed": False,
        "pid": process.pid,
        "state_path": str(INSTALL_STATE_PATH),
        "log_path": str(INSTALL_LOG_PATH),
    }


def read_install_log_tail(lines: int = 30) -> str:
    if not INSTALL_LOG_PATH.exists():
        return ""
    content = INSTALL_LOG_PATH.read_text(encoding="utf-8", errors="ignore").splitlines()
    return "\n".join(content[-max(1, lines):])


def build_status_payload() -> Dict[str, object]:
    payload = read_install_state()
    payload.setdefault("status", "idle")
    payload.setdefault("stage", "")
    payload["running"] = is_install_running()
    payload["pid"] = _read_pid()
    payload["state_path"] = str(INSTALL_STATE_PATH)
    payload["log_path"] = str(INSTALL_LOG_PATH)
    return payload


def main(argv: List[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    if args and args[0] == "--run":
        return run_install()
    if args and args[0] == "--status":
        print(json.dumps(build_status_payload(), ensure_ascii=False, indent=2))
        return 0
    if args and args[0] == "--log":
        tail_lines = 30
        if len(args) > 1:
            try:
                tail_lines = int(args[1])
            except ValueError:
                tail_lines = 30
        print(read_install_log_tail(tail_lines))
        return 0
    if args and args[0] == "--background":
        print(json.dumps(trigger_background_install(force="--force" in args), ensure_ascii=False, indent=2))
        return 0
    return run_install()


if __name__ == "__main__":
    raise SystemExit(main())
