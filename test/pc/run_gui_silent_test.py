#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Silent GUI automation for NeuroLab Hub desktop flows."""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tkinter.messagebox as messagebox

from pc.core.config import get_config, set_config
from pc.desktop_app import DesktopApp
from generate_vision_test_data import generate_dataset

REPORT_PATH = ROOT / "tmp" / "gui_silent_test_report.json"
GUI_LOG_PATH = ROOT / "pc" / "log" / "gui_actions.log"


class GuiSilentTester:
    def __init__(self) -> None:
        self.report_rows: List[Dict[str, Any]] = []
        self.dialog_rows: List[Dict[str, Any]] = []
        self.start_ts = time.time()
        self.app = DesktopApp()
        self.virtual_pi_procs: List[subprocess.Popen[bytes]] = []
        self.original_virtual_pi_enabled = get_config("network.virtual_pi_enabled", "False")
        self.original_virtual_pi_host = get_config("network.virtual_pi_host", "127.0.0.1")
        self.original_virtual_pi_hosts = get_config("network.virtual_pi_hosts", "")
        self.workspace_name = f"gui_silent_{time.strftime('%Y%m%d_%H%M%S')}"
        self.synthetic_report = generate_dataset(self.workspace_name, sample_count=8)
        self.gui_log_marker = f"----- GUI silent automation start {time.strftime('%Y-%m-%d %H:%M:%S')} -----"
        GUI_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        encoding = "utf-8-sig" if not GUI_LOG_PATH.exists() else "utf-8"
        with GUI_LOG_PATH.open("a", encoding=encoding) as fp:
            fp.write(self.gui_log_marker + "\n")
        self.steps: List[tuple[str, Callable[[], None]]] = [
            ("wait_ready", self._step_wait_ready),
            ("open_windows", self._step_open_windows),
            ("cloud_model_config", self._step_cloud_model_config),
            ("run_self_check", self._step_self_check),
            ("camera_start_stop", self._step_camera_start_stop),
            ("training_panel", self._step_training_panel),
            ("websocket_virtual_pi", self._step_websocket_virtual_pi),
            ("archive_window", self._step_archive_window),
            ("finish", self._step_finish),
        ]
        self.step_index = 0

    def _patch_dialogs(self) -> None:
        def _log(kind: str, title: str, message: str) -> None:
            self.dialog_rows.append(
                {
                    "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "kind": kind,
                    "title": title,
                    "message": message,
                }
            )

        messagebox.askyesno = lambda title, message, **kwargs: (_log("askyesno", title, message), False)[1]  # type: ignore[assignment]
        messagebox.showinfo = lambda title, message, **kwargs: (_log("showinfo", title, message), True)[1]  # type: ignore[assignment]
        messagebox.showwarning = lambda title, message, **kwargs: (_log("showwarning", title, message), True)[1]  # type: ignore[assignment]
        messagebox.showerror = lambda title, message, **kwargs: (_log("showerror", title, message), True)[1]  # type: ignore[assignment]

    def run(self) -> int:
        self._patch_dialogs()
        self.app.root.after(300, self._run_next_step)
        self.app.run()
        self._write_report()
        return 0

    def _run_next_step(self) -> None:
        if self.step_index >= len(self.steps):
            return
        name, step = self.steps[self.step_index]
        started = time.time()
        try:
            step()
            self.report_rows.append(
                {
                    "step": name,
                    "status": "pass",
                    "duration_ms": int((time.time() - started) * 1000),
                }
            )
        except Exception as exc:
            self.report_rows.append(
                {
                    "step": name,
                    "status": "fail",
                    "duration_ms": int((time.time() - started) * 1000),
                    "detail": str(exc),
                }
            )
        self.step_index += 1
        self.app.root.after(350, self._run_next_step)

    def _wait_until(self, predicate: Callable[[], bool], timeout: float, message: str) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            self.app.root.update_idletasks()
            self.app.root.update()
            if predicate():
                return
            time.sleep(0.1)
        raise TimeoutError(message)

    def _set_mode(self, mode: str) -> None:
        label = getattr(
            self.app,
            "mode_reverse",
            {},
        ).get(mode, next((key for key, value in self.app.mode_map.items() if value == mode), self.app.mode_combo.get()))
        self.app.mode_var.set(mode)
        values = list(self.app.mode_combo.cget("values") or [])
        if label in values:
            self.app.mode_combo.current(values.index(label))
        else:
            self.app.mode_combo.set(label)
        self.app.mode_combo.event_generate("<<ComboboxSelected>>")
        self.app.root.update_idletasks()
        self.app.root.update()
        self.app._sync_field_visibility()

    def _set_backend(self, backend: str) -> None:
        label = getattr(
            self.app,
            "backend_reverse",
            {},
        ).get(
            backend,
            next((key for key, value in self.app.backend_map.items() if value == backend), self.app.backend_combo.get()),
        )
        self.app.backend_var.set(backend)
        values = list(self.app.backend_combo.cget("values") or [])
        if label in values:
            self.app.backend_combo.current(values.index(label))
        else:
            self.app.backend_combo.set(label)
        self.app.backend_combo.event_generate("<<ComboboxSelected>>")
        self.app._update_model_choices()
        self.app.root.update_idletasks()
        self.app.root.update()

    def _select_real_model(self) -> None:
        values = list(self.app.model_combo.cget("values") or [])
        for index, item in enumerate(values):
            item_text = str(item or "").strip()
            if item_text and "添加自定义模型" not in item_text:
                self.app.model_combo.current(index)
                self.app.root.update_idletasks()
                self.app.root.update()
                return
        if values:
            self.app.model_combo.current(0)
            self.app.root.update_idletasks()
            self.app.root.update()

    def _reserve_port(self) -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            sock.listen(1)
            return int(sock.getsockname()[1])

    def _step_wait_ready(self) -> None:
        self._wait_until(
            lambda: self.app.runtime is not None and bool(self.app.current_state),
            timeout=45.0,
            message="主界面启动超时",
        )

    def _step_open_windows(self) -> None:
        self.app._show_expert_window()
        self.app._show_knowledge_base_window()
        self.app._show_cloud_backend_window()
        self.app._show_training_window("vision")
        self.app._show_manual_window()
        self.app._show_about_window()
        for window in list(self.app.window_refs):
            if window is not None and window.winfo_exists():
                window.destroy()
        self.app.expert_window = None
        self.app.kb_window = None
        self.app.cloud_window = None
        self.app.training_window = None
        self.app.manual_window = None
        self.app.about_window = None
        self.app.copyright_window = None

    def _step_cloud_model_config(self) -> None:
        self.app._show_cloud_backend_window()
        self._wait_until(
            lambda: self.app.cloud_window is not None and self.app.cloud_window.winfo_exists(),
            10.0,
            "模型配置窗口未打开",
        )
        if self.app.cloud_provider_combo is None:
            raise RuntimeError("缺少云端模型提供方下拉框")
        labels = list(self.app.cloud_provider_combo.cget("values") or [])
        target_label = next((item for item in labels if "通义千问" in str(item)), labels[0] if labels else "")
        if not target_label:
            raise RuntimeError("未找到通义千问配置项")
        self.app.cloud_provider_combo.set(target_label)
        self.app._load_selected_cloud_backend_into_form()
        alias = f"静默测试模型_{int(time.time())}"
        if self.app.cloud_api_key_entry is not None:
            self.app.cloud_api_key_entry.delete(0, "end")
            self.app.cloud_api_key_entry.insert(0, "sk-silent-test")
        if self.app.cloud_base_url_entry is not None:
            self.app.cloud_base_url_entry.delete(0, "end")
            self.app.cloud_base_url_entry.insert(0, "https://dashscope.aliyuncs.com/compatible-mode/v1")
        if self.app.cloud_model_entry is not None:
            self.app.cloud_model_entry.delete(0, "end")
            self.app.cloud_model_entry.insert(0, "qwen-max-latest")
        if self.app.cloud_model_alias_entry is not None:
            self.app.cloud_model_alias_entry.delete(0, "end")
            self.app.cloud_model_alias_entry.insert(0, alias)
        self.app._save_cloud_backend_from_form()
        self._wait_until(
            lambda: self.app.cloud_window is None or not self.app.cloud_window.winfo_exists(),
            15.0,
            "模型配置保存后窗口未自动关闭",
        )
        self._set_backend("qwen")
        model_values = [str(item or "").strip() for item in list(self.app.model_combo.cget("values") or [])]
        if alias not in model_values:
            raise RuntimeError(f"新增云端模型未同步到左侧模型选择: {alias}")

    def _step_self_check(self) -> None:
        baseline = len(self.app.current_state.get("self_check", []))
        self.app._run_self_check()
        self._wait_until(
            lambda: len(self.app.current_state.get("self_check", [])) > 0
            and (len(self.app.current_state.get("self_check", [])) != baseline or bool(self.app.current_state.get("self_check"))),
            timeout=45.0,
            message="GUI 自检未完成",
        )

    def _step_camera_start_stop(self) -> None:
        self._set_backend("ollama")
        self._set_mode("camera")
        self._select_real_model()
        self.app.expected_entry.delete(0, "end")
        self.app.expected_entry.insert(0, "1")
        self.app._start_session()
        self._wait_until(
            lambda: str((self.app.current_state.get("session") or {}).get("phase") or "").lower() == "running",
            timeout=35.0,
            message="单机监控未启动",
        )
        time.sleep(6.0)
        self.app._stop_session()
        self._wait_until(
            lambda: str((self.app.current_state.get("session") or {}).get("phase") or "").lower() in {"idle", ""},
            timeout=20.0,
            message="单机监控未停止",
        )

    def _step_training_panel(self) -> None:
        self.app._show_training_window("vision")
        self._wait_until(
            lambda: self.app.training_window is not None and self.app.training_window.winfo_exists(),
            10.0,
            "训练窗口未打开",
        )
        self.app._refresh_training_overview()
        self._wait_until(
            lambda: str((self.app.training_overview or {}).get("latest_workspace") or "").strip() != "",
            timeout=20.0,
            message="训练概览未刷新",
        )
        self.app.training_workspace_entry.delete(0, "end")
        self.app.training_workspace_entry.insert(0, self.workspace_name)
        self.app._generate_training_annotation_samples()
        self._wait_until(
            lambda: len(self.app.training_annotation_items) > 0,
            timeout=15.0,
            message="训练面板未生成测试图片",
        )
        first_iid = self.app.training_annotation_tree.get_children()[0]
        self.app.training_annotation_tree.selection_set(first_iid)
        self.app._on_training_annotation_select()
        if not self.app.training_annotation_boxes:
            self.app.training_annotation_boxes.append(
                {"class_name": "observation", "x1": 80.0, "y1": 80.0, "x2": 260.0, "y2": 260.0}
            )
        self.app._save_training_annotations()
        self.app.training_overview = self.app.runtime.get_training_overview()
        self.app._render_training_overview()
        baseline_jobs = len((self.app.training_overview or {}).get("jobs", []))
        self._wait_until(
            lambda: str((self.app.training_overview or {}).get("latest_workspace") or "").strip() != "",
            timeout=20.0,
            message="训练概览工作区为空",
        )
        self.app._start_pi_training_from_form()
        self._wait_until(
            lambda: self._has_new_training_job(baseline_jobs),
            timeout=60.0,
            message="GUI 未触发 YOLO 训练任务",
        )
        if self.app.training_window is not None and self.app.training_window.winfo_exists():
            self.app.training_window.destroy()
            self.app.training_window = None

    def _step_start_virtual_pi(self) -> None:
        ports = [self._reserve_port(), self._reserve_port()]
        set_config("network.virtual_pi_enabled", "True")
        set_config("network.virtual_pi_host", "127.0.0.1")
        set_config("network.virtual_pi_hosts", ",".join(f"127.0.0.1:{port}" for port in ports))
        for index, port in enumerate(ports, start=1):
            command = [
                sys.executable,
                str(ROOT / "test" / "pi" / "virtual_pi_node.py"),
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--camera-index",
                "-1",
                "--event-name",
                "综合安全巡检",
                "--event-interval",
                "4",
                "--node-id",
                f"gui-silent-{index}",
            ]
            proc = subprocess.Popen(
                command,
                cwd=str(ROOT),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            self.virtual_pi_procs.append(proc)
        time.sleep(3.0)

    def _step_websocket_virtual_pi(self) -> None:
        self._step_start_virtual_pi()
        self._set_backend("ollama")
        self._set_mode("websocket")
        self._select_real_model()
        self.app.expected_entry.delete(0, "end")
        self.app.expected_entry.insert(0, "2")
        self.app._start_session()
        self._wait_until(
            lambda: str((self.app.current_state.get("session") or {}).get("phase") or "").lower() == "running",
            timeout=35.0,
            message="多节点监控未启动",
        )
        self._wait_until(
            lambda: len([row for row in self.app.current_state.get("streams", []) if row.get("status") == "online"]) >= 2,
            timeout=25.0,
            message="虚拟 Pi 未上线",
        )
        self._wait_until(
            lambda: self._has_virtual_pi_result(),
            timeout=30.0,
            message="未看到多节点巡检/专家日志",
        )
        self.app._stop_session()
        self._wait_until(
            lambda: str((self.app.current_state.get("session") or {}).get("phase") or "").lower() in {"idle", ""},
            timeout=20.0,
            message="多节点监控未停止",
        )

    def _step_archive_window(self) -> None:
        self.app._show_archive_window()
        self._wait_until(
            lambda: self.app.archive_window is not None and self.app.archive_window.winfo_exists(),
            10.0,
            "归档窗口未打开",
        )
        self._wait_until(lambda: len(self.app.archive_catalog) > 0, 10.0, "实验归档为空")
        if self.app.archive_window is not None and self.app.archive_window.winfo_exists():
            self.app.archive_window.destroy()
            self.app.archive_window = None

    def _step_finish(self) -> None:
        for proc in self.virtual_pi_procs:
            try:
                proc.terminate()
                proc.communicate(timeout=6)
            except Exception:
                try:
                    proc.kill()
                    proc.communicate(timeout=3)
                except Exception:
                    pass
        self.virtual_pi_procs = []
        set_config("network.virtual_pi_enabled", self.original_virtual_pi_enabled)
        set_config("network.virtual_pi_host", self.original_virtual_pi_host)
        set_config("network.virtual_pi_hosts", self.original_virtual_pi_hosts)
        self.app.root.after(300, self.app._on_close)

    def _latest_runtime_log(self) -> str:
        log_dir = ROOT / "pc" / "log"
        candidates = sorted(log_dir.glob("*_web_console.log"), key=lambda p: p.stat().st_mtime, reverse=True)
        return str(candidates[0]) if candidates else ""

    def _has_new_training_job(self, baseline_jobs: int) -> bool:
        overview = self.app.runtime.get_training_overview()
        self.app.training_overview = overview
        jobs = list(overview.get("jobs", []))
        if len(jobs) <= baseline_jobs:
            return False
        return any(str(job.get("kind") or "") == "pi_detector_finetune" for job in jobs[baseline_jobs:])

    def _has_virtual_pi_result(self) -> bool:
        manager = getattr(self.app.runtime, "manager", None)
        if manager is None:
            return False
        latest = getattr(manager, "node_latest_results", {}) or {}
        for item in latest.values():
            if not isinstance(item, dict):
                continue
            if item.get("event_name") or item.get("text") or item.get("event_id"):
                return True
        return False

    def _tail_gui_log(self) -> List[str]:
        if not GUI_LOG_PATH.exists():
            return []
        payload = GUI_LOG_PATH.read_bytes()
        for encoding in ("utf-8-sig", "utf-8", "gbk", "cp936"):
            try:
                lines = payload.decode(encoding).splitlines()
                break
            except Exception:
                continue
        else:
            lines = payload.decode("utf-8", errors="ignore").splitlines()
        marker_index = 0
        for index, line in enumerate(lines):
            if line.strip() == self.gui_log_marker:
                marker_index = index
        return lines[marker_index:]

    def _write_report(self) -> None:
        payload = {
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "duration_ms": int((time.time() - self.start_ts) * 1000),
            "workspace_name": self.workspace_name,
            "synthetic_dataset": self.synthetic_report,
            "steps": self.report_rows,
            "dialogs": self.dialog_rows,
            "gui_actions_tail": self._tail_gui_log(),
            "latest_runtime_log": self._latest_runtime_log(),
        }
        REPORT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8-sig")


def main() -> int:
    tester = GuiSilentTester()
    return tester.run()


if __name__ == "__main__":
    raise SystemExit(main())
