from __future__ import annotations

import argparse
import asyncio
import json
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Dict, List
from unittest.mock import patch

from pc.core.config import get_config, set_config
from pc.core.expert_closed_loop import parse_pi_expert_ack, parse_pi_expert_packet


def _ensure_release_root_on_path() -> None:
    """保证解压发布包场景下也能导入外层 pi 目录。"""
    current = Path(__file__).resolve()
    checked: set[str] = set()
    for anchor in (current.parent, *current.parents):
        for base in (anchor, anchor.parent):
            key = str(base)
            if key in checked:
                continue
            checked.add(key)
            if (base / "pi" / "testing" / "closed_loop_bridge.py").exists():
                if key not in sys.path:
                    sys.path.insert(0, key)
                loaded = sys.modules.get("pi")
                if loaded is not None:
                    loaded_file = str(getattr(loaded, "__file__", "") or "")
                    loaded_paths = [str(item) for item in list(getattr(loaded, "__path__", []))]
                    if key not in loaded_file and not any(path.startswith(str(base / "pi")) for path in loaded_paths):
                        sys.modules.pop("pi", None)
                return


_ensure_release_root_on_path()

from pi.testing.closed_loop_bridge import PiClosedLoopBridge, default_simulated_scenarios


class SilentDialogRecorder:
    """静默接管 GUI 弹窗，避免测试过程中阻塞。"""

    def __init__(self) -> None:
        self.records: List[Dict[str, Any]] = []
        self._patchers = []

    def __enter__(self) -> "SilentDialogRecorder":
        self._patchers = [
            patch("tkinter.messagebox.showinfo", side_effect=self._showinfo),
            patch("tkinter.messagebox.showwarning", side_effect=self._showwarning),
            patch("tkinter.messagebox.showerror", side_effect=self._showerror),
            patch("tkinter.messagebox.askyesno", side_effect=self._askyesno),
        ]
        for item in self._patchers:
            item.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        for item in reversed(self._patchers):
            item.stop()

    def _record(self, level: str, title: str, message: str) -> bool:
        self.records.append(
            {
                "level": level,
                "title": str(title or ""),
                "message": str(message or ""),
                "timestamp": time.time(),
            }
        )
        return True

    def _showinfo(self, title: str, message: str, **_: Any) -> bool:
        return self._record("info", title, message)

    def _showwarning(self, title: str, message: str, **_: Any) -> bool:
        return self._record("warning", title, message)

    def _showerror(self, title: str, message: str, **_: Any) -> bool:
        return self._record("error", title, message)

    def _askyesno(self, title: str, message: str, **_: Any) -> bool:
        self._record("askyesno", title, message)
        return False


class VirtualPiServer:
    """启动本地虚拟 Pi 节点，驱动 PC-Pi 闭环。"""

    def __init__(self, host: str = "127.0.0.1", port: int = 8761) -> None:
        self.host = host
        self.port = port
        self.bridge = PiClosedLoopBridge()
        self.thread: threading.Thread | None = None
        self.loop: asyncio.AbstractEventLoop | None = None
        self.server: Any = None
        self.stop_event = threading.Event()
        self.ready_event = threading.Event()
        self.error: str = ""
        self.received_commands: List[str] = []
        self.received_events: List[Dict[str, Any]] = []
        self.received_results: List[Dict[str, Any]] = []
        self.acks: List[Dict[str, Any]] = []

    def start(self) -> None:
        self.thread = threading.Thread(target=self._run_loop, daemon=True, name="VirtualPiServer")
        self.thread.start()
        if not self.ready_event.wait(timeout=10):
            raise RuntimeError(self.error or "虚拟 Pi 服务启动超时。")

    def stop(self) -> None:
        self.stop_event.set()
        if self.loop is not None:
            self.loop.call_soon_threadsafe(lambda: None)
        if self.thread is not None:
            self.thread.join(timeout=10)

    def endpoint(self) -> str:
        return f"{self.host}:{self.port}"

    def _run_loop(self) -> None:
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self._serve())
        except Exception as exc:
            self.error = str(exc)
            self.ready_event.set()
        finally:
            pending = [task for task in asyncio.all_tasks(self.loop) if not task.done()]
            for task in pending:
                task.cancel()
            if pending:
                try:
                    self.loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                except Exception:
                    pass
            self.loop.close()

    async def _serve(self) -> None:
        import websockets

        self.server = await websockets.serve(self._handler, self.host, self.port, ping_interval=None)
        self.ready_event.set()
        while not self.stop_event.is_set():
            await asyncio.sleep(0.1)
        self.server.close()
        await self.server.wait_closed()

    async def _handler(self, websocket) -> None:
        await websocket.send("PI_CAPS:" + json.dumps({"has_mic": False, "has_speaker": False}, ensure_ascii=False))
        while not self.stop_event.is_set():
            message = await websocket.recv()
            if not isinstance(message, str):
                continue
            self.received_commands.append(message)
            if message.startswith("CMD:SYNC_POLICY:"):
                policy_raw = message.replace("CMD:SYNC_POLICY:", "", 1)
                policies = json.loads(policy_raw)
                await self._emit_policy_events(websocket, policies)
            elif message.startswith("CMD:EXPERT_RESULT:"):
                payload_raw = message.replace("CMD:EXPERT_RESULT:", "", 1)
                payload = json.loads(payload_raw)
                self.received_results.append(payload)
                ack = {
                    "event_id": str(payload.get("event_id", "")),
                    "status": "ok",
                    "source": "virtual_pi_gui_test",
                }
                await websocket.send(f"PI_EXPERT_ACK:{json.dumps(ack, ensure_ascii=False)}")
                self.acks.append(ack)

    async def _emit_policy_events(self, websocket, policies: Dict[str, Any]) -> None:
        scenarios = default_simulated_scenarios(node_id="1")
        event_policies = list((policies or {}).get("event_policies") or [])
        for scenario in scenarios:
            matched = [row for row in event_policies if str(row.get("event_name") or "") == scenario.event_name]
            if not matched:
                continue
            triggered = self.bridge.trigger_events(
                scenario.frame,
                matched,
                scenario.detected_objects,
                scenario.boxes_dict,
            )
            packets = self.bridge.build_event_packets(triggered, capture_metrics=scenario.capture_metrics)
            for packet in packets:
                parsed_event, _ = parse_pi_expert_packet(packet)
                if parsed_event is not None:
                    self.received_events.append(
                        {
                            "event_id": parsed_event.event_id,
                            "event_name": parsed_event.event_name,
                            "expert_code": parsed_event.expert_code,
                            "policy_name": parsed_event.policy_name,
                            "detected_classes": parsed_event.detected_classes,
                        }
                    )
                await websocket.send(packet)
                await asyncio.sleep(0.15)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="执行 GUI 全模块与 PC-Pi 虚拟闭环测试")
    parser.add_argument(
        "--report-file",
        default=str(Path("D:/NeuroLab/_machine_switch_test/gui_full_closed_loop_report.json")),
        help="测试报告输出路径",
    )
    return parser.parse_args()


def _wait_for(
    pump: Callable[[], None],
    predicate: Callable[[], bool],
    *,
    timeout: float,
    message: str,
) -> None:
    deadline = time.time() + timeout
    last_error = ""
    while time.time() < deadline:
        try:
            pump()
            if predicate():
                return
        except Exception as exc:
            last_error = str(exc)
        time.sleep(0.05)
    detail = f"{message}，等待 {timeout:.1f} 秒后仍未满足。"
    if last_error:
        detail = f"{detail} 最近一次异常: {last_error}"
    raise TimeoutError(detail)


def _set_entry(entry, value: str) -> None:
    entry.delete(0, "end")
    entry.insert(0, value)


def _read_ack_messages(server: VirtualPiServer) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for raw in server.received_commands:
        if not raw.startswith("CMD:EXPERT_RESULT:"):
            continue
        payload_raw = raw.replace("CMD:EXPERT_RESULT:", "", 1)
        payload = json.loads(payload_raw)
        rows.append(payload)
    return rows


def _collect_window_state(app) -> Dict[str, Any]:
    return {
        "manual_window": bool(app.manual_window is not None and app.manual_window.winfo_exists()),
        "knowledge_window": bool(app.kb_window is not None and app.kb_window.winfo_exists()),
        "expert_window": bool(app.expert_window is not None and app.expert_window.winfo_exists()),
        "archive_window": bool(app.archive_window is not None and app.archive_window.winfo_exists()),
        "training_window": bool(app.training_window is not None and app.training_window.winfo_exists()),
        "cloud_window": bool(app.cloud_window is not None and app.cloud_window.winfo_exists()),
        "open_windows": len([item for item in app.window_refs if item.winfo_exists()]),
    }


def _prepare_test_assets(asset_root: Path) -> Dict[str, str]:
    asset_root.mkdir(parents=True, exist_ok=True)
    knowledge_root = asset_root / "knowledge"
    knowledge_root.mkdir(parents=True, exist_ok=True)
    chem_doc = knowledge_root / "chem_gui_test.txt"
    chem_doc.write_text(
        "HF 属于高风险危化品。\n操作时必须佩戴手套、护目镜和实验服。\n检测到未佩戴防护时应立即停止操作并上报。\n",
        encoding="utf-8",
    )
    ppe_doc = knowledge_root / "ppe_gui_test.txt"
    ppe_doc.write_text(
        "进入实验区必须穿实验服、佩戴手套和护目镜。\n若发现人员未按规范佩戴 PPE，应立即整改。\n",
        encoding="utf-8",
    )
    llm_doc = asset_root / "llm_train_gui_test.txt"
    llm_doc.write_text(
        "问: 发现 HF 且未戴手套怎么办？\n答: 立即停止实验操作，远离暴露源并向实验负责人上报。\n\n"
        "问: 实验室 PPE 不完整时应该如何处理？\n答: 立即补齐实验服、手套和护目镜，再继续进入实验流程。\n",
        encoding="utf-8",
    )
    return {
        "chem_doc": str(chem_doc),
        "ppe_doc": str(ppe_doc),
        "llm_doc": str(llm_doc),
        "asset_root": str(asset_root),
    }


def run_gui_full_closed_loop_test(report_file: str) -> Dict[str, Any]:
    from pc.core.expert_manager import expert_manager
    from pc.desktop_app import DesktopApp

    report_path = Path(report_file).resolve()
    asset_root = report_path.parent / "gui_full_closed_loop_assets" / time.strftime("%Y%m%d_%H%M%S")
    assets = _prepare_test_assets(asset_root)
    server = VirtualPiServer()
    dialog_recorder = SilentDialogRecorder()

    preserved_config = {
        "network.virtual_pi_enabled": get_config("network.virtual_pi_enabled", False),
        "network.virtual_pi_host": get_config("network.virtual_pi_host", "127.0.0.1"),
        "network.virtual_pi_hosts": get_config("network.virtual_pi_hosts", ""),
        "session_defaults.project_name": get_config("session_defaults.project_name", ""),
        "session_defaults.experiment_name": get_config("session_defaults.experiment_name", ""),
        "session_defaults.operator_name": get_config("session_defaults.operator_name", ""),
        "session_defaults.tags": get_config("session_defaults.tags", ""),
    }

    report: Dict[str, Any] = {
        "success": False,
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "report_file": str(report_path),
        "assets": assets,
        "steps": [],
        "dialogs": [],
        "virtual_pi": {},
        "windows": {},
        "archive": {},
        "training": {},
        "knowledge": {},
        "experts": {},
        "session": {},
        "errors": [],
    }

    app = None

    def pump() -> None:
        if app is None:
            return
        app.root.update_idletasks()
        app.root.update()

    def add_step(name: str, **payload: Any) -> None:
        row = {"name": name, "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")}
        row.update(payload)
        report["steps"].append(row)

    try:
        server.start()
        set_config("network.virtual_pi_enabled", True)
        set_config("network.virtual_pi_host", server.endpoint())
        set_config("network.virtual_pi_hosts", server.endpoint())

        with dialog_recorder, patch.object(expert_manager, "_build_knowledge_context", lambda *args, **kwargs: {}), patch.object(
            expert_manager,
            "_run_llm_interpreter",
            lambda _expert, _frame, _context, raw_response: raw_response,
        ), patch("pc.voice.voice_interaction.get_voice_interaction", lambda: None):
            app = DesktopApp()
            app.root.withdraw()
            if app.splash is not None and app.splash.winfo_exists():
                app.splash.withdraw()
            app._finish_startup = lambda: None

            _wait_for(
                pump,
                lambda: app.runtime is not None and bool(app.backend_map) and bool(app.current_state.get("self_check")),
                timeout=35,
                message="GUI 启动自检未完成",
            )
            add_step("bootstrap_ready", checks=len(app.current_state.get("self_check", [])))

            app.runtime._configure_backend = lambda: None
            app.runtime._start_background_aux_services = lambda **kwargs: None

            app._show_manual_window()
            app._show_about_and_copyright()
            app._show_cloud_backend_window()
            app._show_knowledge_base_window()
            app._show_expert_window()
            app._show_training_window()
            app._show_archive_window()
            _wait_for(
                pump,
                lambda: all(
                    [
                        app.kb_window is not None and app.kb_window.winfo_exists(),
                        app.expert_window is not None and app.expert_window.winfo_exists(),
                        app.archive_window is not None and app.archive_window.winfo_exists(),
                        app.training_window is not None and app.training_window.winfo_exists(),
                        app.cloud_window is not None and app.cloud_window.winfo_exists(),
                    ]
                ),
                timeout=10,
                message="GUI 模块窗口未全部打开",
            )
            report["windows"] = _collect_window_state(app)
            add_step("windows_opened", **report["windows"])

            app._run_self_check()
            _wait_for(
                pump,
                lambda: len(app.current_state.get("self_check", [])) >= 8,
                timeout=30,
                message="主界面自检结果未刷新",
            )
            add_step("self_check_completed", items=len(app.current_state.get("self_check", [])))

            app.expert_tree.selection_set("safety.chem_safety_expert")
            app._on_expert_tree_select()
            with patch("tkinter.filedialog.askopenfilenames", return_value=[assets["chem_doc"]]):
                app._import_selected_expert_knowledge_text()
            _wait_for(
                pump,
                lambda: "导入完成" in str(app.kb_status_var.get()),
                timeout=45,
                message="危化知识导入未完成",
            )

            app.expert_tree.selection_set("safety.ppe_expert")
            app._on_expert_tree_select()
            with patch("tkinter.filedialog.askopenfilenames", return_value=[assets["ppe_doc"]]):
                app._import_selected_expert_knowledge_text()
            _wait_for(
                pump,
                lambda: len(app.knowledge_catalog) > 0 and "expert.safety.ppe_expert" in {row["scope"] for row in app.knowledge_catalog},
                timeout=45,
                message="PPE 知识导入后目录未刷新",
            )
            report["knowledge"] = {
                "scope_count": len(app.knowledge_catalog),
                "scopes": [row["scope"] for row in app.knowledge_catalog[:12]],
            }
            report["experts"] = {
                "expert_count": len(app.expert_catalog),
                "focus_experts": [
                    row for row in app.expert_catalog if row.get("expert_code") in {"safety.chem_safety_expert", "safety.ppe_expert"}
                ],
            }
            add_step("knowledge_and_expert_ready", scope_count=report["knowledge"]["scope_count"], expert_count=report["experts"]["expert_count"])

            workspace_name = f"gui_full_closed_loop_{time.strftime('%Y%m%d_%H%M%S')}"
            _set_entry(app.training_workspace_entry, workspace_name)
            app._build_training_workspace_from_form()
            _wait_for(
                pump,
                lambda: workspace_name in str((app.training_overview or {}).get("latest_workspace") or ""),
                timeout=30,
                message="训练工作区未生成",
            )

            with patch.object(app, "_pick_paths_for_import", return_value=[assets["llm_doc"]]):
                app._import_llm_dataset_from_dialog()
            _wait_for(
                pump,
                lambda: "LLM 数据导入完成" in str(app.training_status_var.get()),
                timeout=30,
                message="LLM 训练数据未导入完成",
            )

            app._generate_training_annotation_samples()
            _wait_for(
                pump,
                lambda: len(app.training_annotation_items) >= 3,
                timeout=20,
                message="测试标注图片未生成",
            )
            first_image = app.training_annotation_items[0]["name"]
            app.training_annotation_tree.selection_set(first_image)
            app._on_training_annotation_select()
            _wait_for(
                pump,
                lambda: bool(app.training_annotation_current_item),
                timeout=10,
                message="标注图片未载入",
            )
            app.training_annotation_class_entry.delete(0, "end")
            app.training_annotation_class_entry.insert(0, "hazard_box")
            app._on_training_annotation_press(SimpleNamespace(x=120, y=120))
            app._on_training_annotation_drag(SimpleNamespace(x=300, y=260))
            app._on_training_annotation_release(SimpleNamespace(x=300, y=260))
            app._save_training_annotations()
            workspace_dir = str((app.training_overview or {}).get("latest_workspace") or "")
            label_path = Path(workspace_dir) / "pi_detector" / "labels" / "train" / f"{Path(first_image).stem}.txt"
            _wait_for(
                pump,
                lambda: label_path.exists() and bool(label_path.read_text(encoding="utf-8").strip()),
                timeout=15,
                message="标注结果未写入标签文件",
            )
            with patch.object(app, "_pick_paths_for_import", return_value=[str(Path(workspace_dir) / "pi_detector")]):
                app._import_pi_dataset_from_dialog()
            _wait_for(
                pump,
                lambda: "Pi 数据导入完成" in str(app.training_status_var.get()),
                timeout=30,
                message="Pi 数据集导入未完成",
            )
            report["training"] = {
                "workspace_dir": workspace_dir,
                "annotation_image_count": len(app.training_annotation_items),
                "annotation_label_path": str(label_path),
                "training_status": str(app.training_status_var.get()),
                "overview": dict(app.training_overview or {}),
            }
            add_step("training_assets_ready", workspace_dir=workspace_dir, images=len(app.training_annotation_items))

            app.mode_combo.set(app.mode_reverse["websocket"])
            _set_entry(app.expected_entry, "1")
            if app.project_entry is not None:
                _set_entry(app.project_entry, "GUI 全模块闭环测试")
            if app.experiment_entry is not None:
                _set_entry(app.experiment_entry, "虚拟 Pi 闭环")
            if app.operator_entry is not None:
                _set_entry(app.operator_entry, "Codex")
            if app.tags_entry is not None:
                _set_entry(app.tags_entry, "GUI,闭环,虚拟Pi")
            app._sync_field_visibility()
            app._start_session()
            _wait_for(
                pump,
                lambda: str(app.current_state.get("session", {}).get("phase") or "") == "running"
                and int(app.current_state.get("summary", {}).get("online_nodes", 0) or 0) >= 1,
                timeout=40,
                message="监控会话未成功启动或节点未上线",
            )
            _wait_for(
                pump,
                lambda: len(server.received_results) >= 2 and len(server.acks) >= 2,
                timeout=50,
                message="PC-Pi 专家闭环未完成",
            )
            app._stop_session()
            _wait_for(
                pump,
                lambda: str(app.current_state.get("session", {}).get("phase") or "") == "idle",
                timeout=20,
                message="监控会话未停止",
            )
            app._refresh_archive_catalog()
            _wait_for(
                pump,
                lambda: len(app.archive_catalog) > 0,
                timeout=20,
                message="实验档案未刷新",
            )

            latest_archive = app.archive_catalog[0] if app.archive_catalog else {}
            report["archive"] = {
                "archive_count": len(app.archive_catalog),
                "latest": latest_archive,
            }
            report["session"] = {
                "summary": app.current_state.get("summary", {}),
                "session": app.current_state.get("session", {}),
            }
            report["virtual_pi"] = {
                "endpoint": server.endpoint(),
                "received_commands": list(server.received_commands),
                "received_events": list(server.received_events),
                "received_results": list(server.received_results),
                "acks": list(server.acks),
                "sent_result_count": len(_read_ack_messages(server)),
            }
            add_step(
                "pc_pi_closed_loop_completed",
                online_nodes=int(report["session"]["summary"].get("online_nodes", 0) or 0),
                event_count=len(server.received_events),
                result_count=len(server.received_results),
                ack_count=len(server.acks),
            )

        report["dialogs"] = list(dialog_recorder.records)
        report["success"] = True
        report["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        return report
    except Exception as exc:
        report["errors"].append(str(exc))
        report["dialogs"] = list(dialog_recorder.records)
        report["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        return report
    finally:
        for key, value in preserved_config.items():
            set_config(key, value)
        if app is not None:
            try:
                app._on_close()
            except Exception:
                pass
        server.stop()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    args = _parse_args()
    report = run_gui_full_closed_loop_test(args.report_file)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
