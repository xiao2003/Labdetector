# -*- coding: utf-8 -*-
"""安装包首启 smoke 验证脚本。"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="验证安装包安装后首次启动行为。")
    parser.add_argument("--installer", required=True, help="安装包路径")
    parser.add_argument("--install-dir", required=True, help="安装目标目录")
    parser.add_argument("--report", required=True, help="报告输出路径")
    parser.add_argument("--wait-seconds", type=int, default=25, help="启动后观察秒数")
    parser.add_argument("--clear-runtime-state", action="store_true", help="启动前清理本地固定管家层运行时状态")
    return parser.parse_args()


def _run_installer(installer: Path, install_dir: Path, install_log_path: Path) -> tuple[int, str, str]:
    install_dir.parent.mkdir(parents=True, exist_ok=True)
    install_log_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        str(installer),
        "/VERYSILENT",
        "/SUPPRESSMSGBOXES",
        "/NORESTART",
        f"/DIR={install_dir}",
        f"/LOG={install_log_path}",
    ]
    completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return int(completed.returncode), str(completed.stdout or ""), str(completed.stderr or "")


def _is_admin() -> bool:
    """检测当前进程是否具有管理员权限。"""
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _classify_install_result(
    *,
    install_exit_code: int,
    exe_exists: bool,
    installer_log_exists: bool,
    is_admin: bool,
) -> dict[str, Any]:
    """区分真实安装失败与当前会话权限不足导致的阻塞。"""
    blocked = False
    blocked_reason = ""
    if install_exit_code != 0 and not exe_exists and not installer_log_exists and not is_admin:
        blocked = True
        blocked_reason = "installer_requires_admin"
    return {
        "blocked": blocked,
        "blocked_reason": blocked_reason,
    }


def _list_pythonw() -> set[tuple[int, str]]:
    command = [
        "powershell",
        "-Command",
        "Get-Process pythonw -ErrorAction SilentlyContinue | Select-Object Id,StartTime | ConvertTo-Json -Compress",
    ]
    completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    raw = str(completed.stdout or "").strip()
    if not raw:
        return set()
    payload: Any = json.loads(raw)
    if isinstance(payload, dict):
        payload = [payload]
    records: set[tuple[int, str]] = set()
    for item in payload:
        records.add((int(item["Id"]), str(item["StartTime"])))
    return records


def _runtime_state_path() -> Path:
    local_appdata = Path(os.environ.get("LOCALAPPDATA") or "").expanduser()
    return local_appdata / "NeuroLabHub" / "orchestrator" / "state.json"


def _runtime_root() -> Path:
    local_appdata = Path(os.environ.get("LOCALAPPDATA") or "").expanduser()
    return local_appdata / "NeuroLabHub" / "orchestrator"


def _clear_runtime_state() -> None:
    root = _runtime_root()
    if root.exists():
        import shutil

        shutil.rmtree(root, ignore_errors=True)


def _read_runtime_state() -> dict[str, Any]:
    path = _runtime_state_path()
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if isinstance(payload, dict):
        return payload
    return {}


def main() -> int:
    args = _parse_args()
    installer = Path(args.installer).resolve()
    install_dir = Path(args.install_dir).resolve()
    report_path = Path(args.report).resolve()
    exe_path = install_dir / "NeuroLab Hub.exe"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    installer_log_path = report_path.with_suffix(".installer.log")
    is_admin = _is_admin()

    if args.clear_runtime_state:
        _clear_runtime_state()

    before_pythonw = _list_pythonw()
    install_exit_code, install_stdout, install_stderr = _run_installer(installer, install_dir, installer_log_path)
    started_at = time.strftime("%Y-%m-%d %H:%M:%S")
    process_started = False
    launcher_pid: int | None = None
    launcher_alive = False
    new_pythonw: list[dict[str, Any]] = []
    observed_states: list[dict[str, Any]] = []

    if exe_path.exists():
        launcher = subprocess.Popen([str(exe_path)], cwd=str(install_dir))
        process_started = True
        launcher_pid = int(launcher.pid)
        wait_seconds = max(int(args.wait_seconds), 1)
        for second in range(wait_seconds):
            time.sleep(1)
            current_state = _read_runtime_state()
            if current_state:
                observed_states.append({
                    "t": second + 1,
                    "status": str(current_state.get("status") or ""),
                    "planner_backend": str(current_state.get("planner_backend") or ""),
                    "reason": str(current_state.get("reason") or ""),
                })
        launcher_alive = launcher.poll() is None
        after_pythonw = _list_pythonw()
        for pid, started in sorted(after_pythonw - before_pythonw):
            new_pythonw.append({"pid": pid, "start_time": started})
    final_state = _read_runtime_state()
    install_classification = _classify_install_result(
        install_exit_code=install_exit_code,
        exe_exists=exe_path.exists(),
        installer_log_exists=installer_log_path.exists(),
        is_admin=is_admin,
    )
    payload = {
        "started_at": started_at,
        "installer": str(installer),
        "install_dir": str(install_dir),
        "is_admin": is_admin,
        "install_exit_code": install_exit_code,
        "install_ok": install_exit_code == 0,
        "install_blocked": bool(install_classification.get("blocked", False)),
        "install_blocked_reason": str(install_classification.get("blocked_reason", "")),
        "install_stdout": install_stdout.strip(),
        "install_stderr": install_stderr.strip(),
        "installer_log_path": str(installer_log_path),
        "exe_exists": exe_path.exists(),
        "process_started": process_started,
        "launcher_pid": launcher_pid,
        "launcher_alive_after_wait": launcher_alive,
        "new_pythonw_processes": new_pythonw,
        "wait_seconds": int(args.wait_seconds),
        "runtime_state_path": str(_runtime_state_path()),
        "runtime_state_after_wait": final_state,
        "runtime_state_timeline": observed_states,
        "finished_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
