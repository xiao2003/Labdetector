#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Lightweight bootstrap entry for packaged NeuroLab Hub."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import shutil
import time
from pathlib import Path
from typing import Dict, Iterable, List

try:
    import tkinter as tk
    from tkinter import ttk
except Exception:  # pragma: no cover
    tk = None
    ttk = None


GUI_CORE_DEPENDENCY_MAP: Dict[str, str] = {
    "numpy": "numpy",
    "cv2": "opencv-python",
    "PIL": "pillow",
    "websockets": "websockets",
    "requests": "requests",
}

PYTHON_INSTALL_COMMAND = [
    "winget",
    "install",
    "--id",
    "Python.Python.3.11",
    "-e",
    "--accept-package-agreements",
    "--accept-source-agreements",
    "--disable-interactivity",
]


def _is_usable_python(path: str) -> bool:
    candidate = str(path or "").strip()
    if not candidate:
        return False
    try:
        resolved = Path(candidate).resolve()
    except Exception:
        return False
    # WindowsApps 中的 python 别名在部分机器上不可直接用于子进程拉起。
    if "windowsapps" in str(resolved).lower():
        return False
    if not resolved.exists():
        return False
    creation_flags = 0x08000000 if os.name == "nt" else 0
    try:
        probe = subprocess.run(
            [str(resolved), "-c", "import sys; print(sys.version_info[:2])"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=8,
            creationflags=creation_flags,
        )
        return probe.returncode == 0
    except Exception:
        return False


def _launcher_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _app_root() -> Path:
    bundled = _launcher_dir() / "APP"
    return bundled if bundled.exists() else _launcher_dir()


def _python_root() -> Path:
    return _app_root() / "python_runtime"


def _system_python_candidates(windowed: bool = False) -> List[str]:
    exe_name = "pythonw.exe" if windowed else "python.exe"
    candidates: List[Path] = []
    local_appdata = str(os.environ.get("LOCALAPPDATA") or "").strip()
    program_files = str(os.environ.get("ProgramFiles") or "").strip()
    program_files_x86 = str(os.environ.get("ProgramFiles(x86)") or "").strip()
    for root in (local_appdata, program_files, program_files_x86):
        if not root:
            continue
        root_path = Path(root)
        candidates.extend(
            [
                root_path / "Programs" / "Python" / "Python311" / exe_name,
                root_path / "Programs" / "Python" / "Python312" / exe_name,
                root_path / "Programs" / "Python" / "Python313" / exe_name,
                root_path / "Python311" / exe_name,
                root_path / "Python312" / exe_name,
                root_path / "Python313" / exe_name,
            ]
        )
    return [str(item) for item in candidates]


def _python_exe(windowed: bool = False) -> str:
    preferred = _python_root() / ("pythonw.exe" if windowed else "python.exe")
    if _is_usable_python(str(preferred)):
        return str(preferred)
    if not getattr(sys, "frozen", False) and _is_usable_python(str(Path(sys.executable).resolve())):
        return str(Path(sys.executable).resolve())
    for candidate in _system_python_candidates(windowed=windowed):
        if _is_usable_python(candidate):
            return candidate
    candidates = ["pythonw.exe", "python.exe", "py.exe"] if windowed else ["python.exe", "py.exe", "pythonw.exe"]
    for candidate in candidates:
        resolved = shutil.which(candidate)
        if resolved and _is_usable_python(resolved):
            return resolved
    if not getattr(sys, "frozen", False):
        return str(Path(sys.executable).resolve())
    raise RuntimeError("未检测到可用 Python 运行时，请先安装 Python 3.11 后重新启动。")


def _find_system_python() -> str:
    """查找系统可用 Python，用于轻量入口首次拉起主程序。"""
    for candidate in _system_python_candidates(windowed=False):
        if _is_usable_python(candidate):
            return candidate
    for candidate in ("python.exe", "py.exe"):
        resolved = shutil.which(candidate)
        if resolved and _is_usable_python(resolved):
            return resolved
    return ""


def _ensure_system_python(progress: BootstrapProgress) -> None:
    """确保系统已安装 Python 3.11；轻量入口不再随包携带完整运行时。"""
    if _find_system_python():
        return
    progress.update(28, "正在安装 Python 运行环境", "首次启动：检测到系统缺少 Python 3.11，正在自动安装")
    result = _run_hidden(PYTHON_INSTALL_COMMAND, timeout=3600)
    if result.returncode != 0:
        raise RuntimeError("未检测到 Python 3.11，且自动安装失败，请联网后重试。")
    if not _find_system_python():
        raise RuntimeError("Python 3.11 安装完成后仍未检测到解释器，请重新启动软件。")


def _launcher_script() -> Path:
    candidate = _app_root() / "launcher.py"
    if candidate.exists():
        return candidate
    return _launcher_dir() / "launcher.py"


def _runtime_env() -> Dict[str, str]:
    env = os.environ.copy()
    app_root = _app_root()
    deps_root = _deps_root()
    python_root = _python_root()
    # 先加载用户目录依赖，再加载应用目录，避免安装目录只读导致首次启动失败。
    python_path_parts = [str(deps_root), str(app_root)]
    existing_pythonpath = str(env.get("PYTHONPATH") or "").strip()
    if existing_pythonpath:
        python_path_parts.append(existing_pythonpath)
    env["PYTHONPATH"] = os.pathsep.join(python_path_parts)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    env["NEUROLAB_BOOTSTRAP_EXE_NAME"] = Path(sys.argv[0]).name
    env["NEUROLAB_SKIP_DESKTOP_SPLASH"] = "1"
    if python_root.exists():
        env["PYTHONHOME"] = str(python_root)
    return env


def _deps_root() -> Path:
    local_appdata = str(os.environ.get("LOCALAPPDATA") or "").strip()
    if local_appdata:
        return Path(local_appdata) / "NeuroLab Hub" / "python_deps"
    return _app_root()


def _run_hidden(command: List[str], timeout: int = 1200) -> subprocess.CompletedProcess[str]:
    creation_flags = 0x08000000 if os.name == "nt" else 0
    return subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="ignore",
        timeout=timeout,
        env=_runtime_env(),
        creationflags=creation_flags,
    )


def _launcher_creation_flags() -> int:
    if os.name != "nt":
        return 0
    create_no_window = 0x08000000
    detached_process = 0x00000008
    create_new_process_group = 0x00000200
    return create_no_window | detached_process | create_new_process_group


def _wait_for_child_ready(
    process: subprocess.Popen[str],
    timeout: float = 12.0,
    settle_seconds: float = 1.2,
) -> None:
    """确认主进程未在启动瞬间退出，避免启动器无意义地长时间停留。"""
    deadline = time.time() + timeout
    settle_deadline = time.time() + max(0.2, settle_seconds)
    while time.time() < deadline:
        return_code = process.poll()
        if return_code is not None:
            raise RuntimeError(f"主程序启动失败，退出码 {return_code}。")
        if time.time() >= settle_deadline:
            return
        time.sleep(0.15)


def _load_identity() -> Dict[str, str]:
    identity_path = _app_root() / "project_identity.json"
    if identity_path.exists():
        try:
            return json.loads(identity_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"short_name": "NeuroLab Hub"}


def _version_text() -> str:
    for candidate in (_app_root() / "VERSION", _launcher_dir() / "VERSION"):
        if candidate.exists():
            try:
                value = candidate.read_text(encoding="utf-8").strip().lstrip("\ufeff")
                if value:
                    return value
            except Exception:
                pass
    return "vUnknown"


def _title_text() -> str:
    return str(_load_identity().get("short_name") or "NeuroLab Hub")


def _is_silent_bootstrap() -> bool:
    args = [str(item).strip().lower() for item in sys.argv[1:]]
    if "--silent-bootstrap" in args:
        return True
    if "--smoke-test-file" in args:
        return True
    env_value = str(os.environ.get("NEUROLAB_BOOTSTRAP_SILENT") or "").strip().lower()
    return env_value in {"1", "true", "yes", "on"}


def _smoke_test_output_path() -> str:
    args = sys.argv[1:]
    for index, item in enumerate(args):
        if str(item).strip().lower() == "--smoke-test-file":
            if index + 1 < len(args):
                return str(args[index + 1]).strip()
            return ""
    return str(os.environ.get("NEUROLAB_SMOKE_TEST_FILE") or "").strip()


def _is_smoke_test_mode() -> bool:
    return bool(_smoke_test_output_path())


def _ensure_pip() -> None:
    probe = _run_hidden([str(_python_exe()), "-m", "pip", "--version"], timeout=120)
    if probe.returncode == 0:
        return
    _run_hidden([str(_python_exe()), "-m", "ensurepip", "--upgrade"], timeout=300)


def _probe_missing_modules(module_names: Iterable[str]) -> List[str]:
    names = [name for name in module_names if name]
    command = [
        str(_python_exe()),
        "-c",
        "import importlib.util, json, sys; "
        "print(json.dumps({name: importlib.util.find_spec(name) is not None for name in sys.argv[1:]}, ensure_ascii=False))",
        *names,
    ]
    result = _run_hidden(command, timeout=120)
    if result.returncode != 0 or not result.stdout.strip():
        return names
    try:
        parsed = json.loads(result.stdout.strip().splitlines()[-1])
    except Exception:
        return names
    return [name for name, ok in parsed.items() if not ok]


class BootstrapProgress:
    def __init__(self) -> None:
        self.root = None
        self.progress = None
        self.title_var = None
        self.detail_var = None
        self._closed = False

        if _is_silent_bootstrap():
            return
        if tk is None or ttk is None:
            return

        self.root = tk.Tk()
        self.root.title(f"{_title_text()} 正在启动")
        self.root.configure(bg="#0f1720")
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self._close)

        container = tk.Frame(self.root, bg="#0f1720", padx=22, pady=20)
        container.pack(fill="both", expand=True)

        title = tk.Label(
            container,
            text=_title_text(),
            font=("Microsoft YaHei UI", 26, "bold"),
            fg="#f8fafc",
            bg="#0f1720",
        )
        title.pack(anchor="w")
        subtitle = tk.Label(
            container,
            text=f"桌面版 {_version_text()}",
            font=("Microsoft YaHei UI", 12),
            fg="#cbd5e1",
            bg="#0f1720",
        )
        subtitle.pack(anchor="w", pady=(2, 0))

        self.title_var = tk.StringVar(value="12% 正在检查运行环境")
        self.detail_var = tk.StringVar(value="环境准备：正在定位 APP 目录与 Python 运行时")
        tk.Label(
            container,
            textvariable=self.title_var,
            font=("Microsoft YaHei UI", 12, "bold"),
            fg="#67e8f9",
            bg="#0f1720",
        ).pack(anchor="w", pady=(18, 6))
        tk.Label(
            container,
            textvariable=self.detail_var,
            font=("Microsoft YaHei UI", 11),
            fg="#e2e8f0",
            bg="#0f1720",
        ).pack(anchor="w")

        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure(
            "Bootstrap.Horizontal.TProgressbar",
            troughcolor="#d6d3d1",
            background="#22c55e",
            bordercolor="#d6d3d1",
            lightcolor="#22c55e",
            darkcolor="#22c55e",
        )
        self.progress = ttk.Progressbar(
            container,
            style="Bootstrap.Horizontal.TProgressbar",
            orient="horizontal",
            mode="determinate",
            maximum=100,
            length=520,
        )
        self.progress.pack(anchor="w", pady=(16, 0))
        self.progress["value"] = 12

        self.root.update_idletasks()
        width = self.root.winfo_reqwidth()
        height = self.root.winfo_reqheight()
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        left = max(0, (screen_w - width) // 2)
        top = max(0, (screen_h - height) // 2)
        self.root.geometry(f"{width}x{height}+{left}+{top}")

    def update(self, percent: float, title: str, detail: str) -> None:
        if self.root is None or self._closed:
            return
        self.progress["value"] = percent
        self.title_var.set(f"{percent:.0f}% {title}")
        self.detail_var.set(detail)
        self.root.update_idletasks()
        self.root.update()

    def _close(self) -> None:
        self._closed = True
        if self.root is not None:
            self.root.destroy()

    def close(self) -> None:
        if self.root is not None and not self._closed:
            self.root.destroy()
            self._closed = True


def _install_packages(packages: Iterable[str], progress: BootstrapProgress) -> None:
    package_list = [item for item in packages if item]
    if not package_list:
        return
    deps_root = _deps_root()
    deps_root.mkdir(parents=True, exist_ok=True)
    progress.update(52, "正在准备桌面依赖", "核心依赖：正在准备 pip 环境")
    _ensure_pip()
    command = [
        str(_python_exe()),
        "-m",
        "pip",
        "install",
        "--upgrade",
        "--no-warn-script-location",
        "--disable-pip-version-check",
        "--target",
        str(deps_root),
        *package_list,
    ]
    progress.update(68, "正在下载必需依赖", "核心依赖：首次启动将自动补齐桌面组件")
    result = _run_hidden(command, timeout=3600)
    if result.returncode != 0:
        lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        summary = "；".join(lines[-3:]) if lines else "无可用安装日志"
        raise RuntimeError(f"首次依赖安装失败，请检查网络或写入权限后重试。安装日志：{summary}")


def _launch_main() -> None:
    python_gui = _python_exe(windowed=True)
    python_cli = _python_exe(windowed=False)
    forward_args = [str(item) for item in sys.argv[1:]]
    smoke_file = _smoke_test_output_path()
    lower_args = [item.strip().lower() for item in forward_args]
    if smoke_file and "--smoke-test-file" not in lower_args:
        forward_args.extend(["--smoke-test-file", smoke_file])
    creation_flags = _launcher_creation_flags()
    env = _runtime_env()
    command = [python_gui or python_cli, str(_launcher_script()), *forward_args]
    process = subprocess.Popen(
        command,
        cwd=str(_app_root()),
        env=env,
        creationflags=creation_flags,
        close_fds=(os.name != "nt"),
    )
    _wait_for_child_ready(process)


def main() -> int:
    progress = BootstrapProgress()
    try:
        progress.update(18, "正在检查运行环境", "环境准备：正在检查核心桌面组件")
        _ensure_system_python(progress)
        if not _is_smoke_test_mode():
            missing_modules = _probe_missing_modules(GUI_CORE_DEPENDENCY_MAP.keys())
            if missing_modules:
                packages = [GUI_CORE_DEPENDENCY_MAP[name] for name in missing_modules]
                _install_packages(packages, progress)
        progress.update(99, "正在启动工作台界面", "界面加载：核心依赖已就绪")
        _launch_main()
        progress.update(100, "主界面准备完成", "启动完成：NeuroLab Hub 即将显示主界面")
        return 0
    finally:
        progress.close()


if __name__ == "__main__":
    raise SystemExit(main())
