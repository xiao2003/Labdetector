#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Lightweight bootstrap entry for packaged NeuroLab Hub."""

from __future__ import annotations

import json
import os
import subprocess
import sys
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


def _launcher_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _app_root() -> Path:
    bundled = _launcher_dir() / "APP"
    return bundled if bundled.exists() else _launcher_dir()


def _python_root() -> Path:
    return _app_root() / "python_runtime"


def _python_exe(windowed: bool = False) -> Path:
    preferred = _python_root() / ("pythonw.exe" if windowed else "python.exe")
    if preferred.exists():
        return preferred
    return Path(sys.executable).resolve()


def _launcher_script() -> Path:
    candidate = _app_root() / "launcher.py"
    if candidate.exists():
        return candidate
    return _launcher_dir() / "launcher.py"


def _runtime_env() -> Dict[str, str]:
    env = os.environ.copy()
    app_root = _app_root()
    python_root = _python_root()
    env["PYTHONPATH"] = str(app_root)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    env["NEUROLAB_BOOTSTRAP_EXE_NAME"] = Path(sys.argv[0]).name
    if python_root.exists():
        env["PYTHONHOME"] = str(python_root)
    return env


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
    progress.update(52, "正在准备桌面依赖", "核心依赖：正在准备 pip 环境")
    _ensure_pip()
    command = [
        str(_python_exe()),
        "-m",
        "pip",
        "install",
        "--upgrade",
        "--no-warn-script-location",
        "--target",
        str(_app_root()),
        *package_list,
    ]
    progress.update(68, "正在下载必需依赖", "核心依赖：首次启动将自动补齐桌面组件")
    result = _run_hidden(command, timeout=3600)
    if result.returncode != 0:
        raise RuntimeError("首次依赖安装失败，请检查网络后重新执行软件自检。")


def _launch_main() -> None:
    python_gui = _python_exe(windowed=True)
    python_cli = _python_exe(windowed=False)
    command = [str(python_gui if python_gui.exists() else python_cli), str(_launcher_script()), *sys.argv[1:]]
    creation_flags = 0x08000000 if os.name == "nt" else 0
    subprocess.Popen(command, cwd=str(_app_root()), env=_runtime_env(), creationflags=creation_flags)


def main() -> int:
    progress = BootstrapProgress()
    try:
        progress.update(18, "正在检查运行环境", "环境准备：正在检查核心桌面组件")
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
