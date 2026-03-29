from __future__ import annotations

import argparse
import asyncio
import json
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import patch

from pc.core.expert_closed_loop import parse_pi_expert_packet


def _resolve_release_root_with_pi() -> Path | None:
    """定位包含完整 pi 测试与语音资源的发布根目录。"""
    current = Path(__file__).resolve()
    checked: set[str] = set()
    for anchor in (current.parent, *current.parents):
        for base in (anchor, anchor.parent):
            key = str(base)
            if key in checked:
                continue
            checked.add(key)
            if (base / "pi" / "testing" / "closed_loop_bridge.py").exists():
                return base
    release_root = current.parents[2] / "release"
    if release_root.exists():
        for child in sorted(release_root.iterdir(), key=lambda item: item.stat().st_mtime, reverse=True):
            if (child / "pi" / "testing" / "closed_loop_bridge.py").exists():
                return child
    return None


def _resolve_voice_model_path() -> Path | None:
    """优先定位真实可用的 Vosk 模型目录。"""
    roots: List[Path] = []
    base = _resolve_release_root_with_pi()
    if base is not None:
        roots.append(base)
    current = Path(__file__).resolve()
    release_candidates = [current.parents[2] / "release", current.parents[3] / "release"]
    for release_root in release_candidates:
        if release_root.exists():
            roots.extend(
                sorted(
                    [item for item in release_root.iterdir() if item.is_dir()],
                    key=lambda item: item.stat().st_mtime,
                    reverse=True,
                )
            )
    for root in roots:
        model_dir = root / "pi" / "voice" / "model"
        if (model_dir / "am" / "final.mdl").exists():
            return model_dir
    return None


def _ensure_release_root_on_path() -> None:
    """保证解压发布包场景下也能导入外层 pi 目录。"""
    base = _resolve_release_root_with_pi()
    if base is None:
        return
    key = str(base)
    if key not in sys.path:
        sys.path.insert(0, key)
    loaded = sys.modules.get("pi")
    if loaded is not None:
        loaded_file = str(getattr(loaded, "__file__", "") or "")
        loaded_paths = [str(item) for item in list(getattr(loaded, "__path__", []))]
        if key not in loaded_file and not any(path.startswith(str(base / "pi")) for path in loaded_paths):
            sys.modules.pop("pi", None)


_ensure_release_root_on_path()

from pi.testing.audio_assets import build_dynamic_voice_suite
from pi.testing.audio_replay import replay_voice_plan
from pi.testing.closed_loop_bridge import PiClosedLoopBridge, default_simulated_scenarios
from pi.voice.interaction import PiVoiceInteraction
from pi.voice.recognizer import PiVoiceRecognizer


class VirtualAudioVoicePiServer:
    """模拟 Pi 音频输入、语音上行与视觉事件上行的闭环节点。"""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8762,
        *,
        node_id: str = "1",
        voice_sample_keys: List[str] | None = None,
        visual_event_name: str = "危化品识别",
    ) -> None:
        self.host = host
        self.port = port
        self.node_id = str(node_id)
        self.voice_sample_keys = list(voice_sample_keys or ["wake_word", "dynamic_qa_status", "wake_word", "fixed_model_risk"])
        self.visual_event_name = visual_event_name
        self.bridge = PiClosedLoopBridge()
        self.loop: asyncio.AbstractEventLoop | None = None
        self.thread: threading.Thread | None = None
        self.server = None
        self.stop_event = threading.Event()
        self.ready_event = threading.Event()
        self.error = ""
        self.received_commands: List[str] = []
        self.received_tts: List[str] = []
        self.received_expert_results: List[Dict[str, Any]] = []
        self.sent_voice_commands: List[str] = []
        self.sent_events: List[Dict[str, Any]] = []
        self.acks: List[Dict[str, Any]] = []
        self.audio_records: List[Dict[str, Any]] = []
        self.audio_suite: Dict[str, Dict[str, Any]] = {}
        self._voice_sent = False

    def endpoint(self) -> str:
        return f"{self.host}:{self.port}"

    def start(self) -> None:
        self.thread = threading.Thread(target=self._run_loop, daemon=True, name="VirtualAudioVoicePiServer")
        self.thread.start()
        if not self.ready_event.wait(timeout=10):
            raise RuntimeError(self.error or "虚拟 Pi 音频节点启动超时。")

    def stop(self) -> None:
        self.stop_event.set()
        if self.loop is not None:
            self.loop.call_soon_threadsafe(lambda: None)
        if self.thread is not None:
            self.thread.join(timeout=10)

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
        await websocket.send("PI_CAPS:" + json.dumps({"has_mic": True, "has_speaker": True}, ensure_ascii=False))
        while not self.stop_event.is_set():
            message = await websocket.recv()
            if not isinstance(message, str):
                continue
            self.received_commands.append(message)
            if message.startswith("CMD:SYNC_CONFIG:") and not self._voice_sent:
                payload = json.loads(message.replace("CMD:SYNC_CONFIG:", "", 1))
                await self._emit_audio_commands(websocket, str(payload.get("wake_word") or "小爱同学"))
                self._voice_sent = True
            elif message.startswith("CMD:SYNC_POLICY:"):
                await self._emit_visual_event(websocket, json.loads(message.replace("CMD:SYNC_POLICY:", "", 1)))
            elif message.startswith("CMD:TTS:"):
                self.received_tts.append(message.replace("CMD:TTS:", "", 1))
            elif message.startswith("CMD:EXPERT_RESULT:"):
                payload = json.loads(message.replace("CMD:EXPERT_RESULT:", "", 1))
                self.received_expert_results.append(payload)
                ack = {
                    "event_id": str(payload.get("event_id", "")),
                    "status": "ok",
                    "source": "virtual_audio_voice_pi",
                }
                self.acks.append(ack)
                await websocket.send(f"PI_EXPERT_ACK:{json.dumps(ack, ensure_ascii=False)}")

    async def _emit_audio_commands(self, websocket, wake_word: str) -> None:
        asset_root = Path("release/virtual_audio_voice_assets") / f"node_{self.node_id}"
        self.audio_suite = build_dynamic_voice_suite(asset_root, wake_word=wake_word)
        model_dir = _resolve_voice_model_path()
        if model_dir is None:
            raise RuntimeError("未找到包含完整 Vosk 模型的发布目录。")
        model_path = str(model_dir)
        sample_plan = [self.audio_suite[key] for key in self.voice_sample_keys]
        replay = replay_voice_plan(
            recognizer_cls=PiVoiceRecognizer,
            interaction_cls=PiVoiceInteraction,
            model_path=model_path,
            wake_word=wake_word,
            sample_plan=sample_plan,
        )
        self.audio_records = list(replay["records"])
        for row in replay["outgoing_messages"]:
            payload = str(row["payload"] or "")
            await websocket.send(payload)
            if payload.startswith("PI_VOICE_COMMAND:"):
                self.sent_voice_commands.append(payload.replace("PI_VOICE_COMMAND:", "", 1))
            await asyncio.sleep(0.05)

    async def _emit_visual_event(self, websocket, policies: Dict[str, Any]) -> None:
        scenarios = default_simulated_scenarios(node_id=self.node_id)
        target = next((row for row in scenarios if row.event_name == self.visual_event_name), None)
        if target is None:
            return
        event_policies = [row for row in list((policies or {}).get("event_policies") or []) if str(row.get("event_name") or "") == target.event_name]
        if not event_policies:
            return
        triggered = self.bridge.trigger_events(
            target.frame,
            event_policies,
            target.detected_objects,
            target.boxes_dict,
        )
        packets = self.bridge.build_event_packets(triggered, capture_metrics=target.capture_metrics)
        for packet in packets[:1]:
            parsed_event, _ = parse_pi_expert_packet(packet)
            if parsed_event is not None:
                self.sent_events.append(
                    {
                        "event_id": parsed_event.event_id,
                        "event_name": parsed_event.event_name,
                        "expert_code": parsed_event.expert_code,
                        "policy_name": parsed_event.policy_name,
                    }
                )
            await websocket.send(packet)
            await asyncio.sleep(0.05)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="执行虚拟音频语音 + 视觉闭环测试")
    parser.add_argument(
        "--report-file",
        default=str(Path("release/virtual_text_voice_closed_loop_report.json")),
        help="测试报告输出路径",
    )
    return parser.parse_args()


def _wait_for(predicate, *, timeout: float, message: str) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return
        time.sleep(0.1)
    raise TimeoutError(message)


def run_virtual_text_voice_closed_loop_test(report_file: str) -> Dict[str, Any]:
    from pc.webui.runtime import LabDetectorRuntime

    report_path = Path(report_file).resolve()
    server = VirtualAudioVoicePiServer()
    report: Dict[str, Any] = {
        "success": False,
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "report_file": str(report_path),
        "steps": [],
        "server": {},
        "runtime_state": {},
        "errors": [],
    }

    runtime = None

    def add_step(name: str, **payload: Any) -> None:
        row = {"name": name, "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")}
        row.update(payload)
        report["steps"].append(row)

    try:
        server.start()
        with patch("pc.communication.network_scanner.scan_multi_nodes", lambda expected_nodes: {"1": server.endpoint()}), patch(
            "pc.core.orchestrator.ask_assistant_with_rag",
            lambda frame, question, rag_context, model_name: f"离线答复：已收到指令“{question}”，当前系统运行正常。",
        ), patch(
            "pc.voice.voice_interaction.VoiceInteraction._extract_knowledge_with_llm",
            lambda self, transcript: [],
        ), patch(
            "pc.voice.voice_interaction.get_voice_interaction",
            lambda: None,
        ), patch(
            "pc.core.expert_manager.expert_manager.route_and_analyze",
            lambda event_name, frame, context, allowed_expert_codes=None, trigger_mode=None: "极度危险：识别到 HF 且未检测到手套，请立即停止操作并上报。",
        ):
            runtime = LabDetectorRuntime()
            add_step("runtime_ready", version=runtime.version)

            runtime.start_session(
                {
                    "ai_backend": "ollama",
                    "selected_model": "gemma3:4b",
                    "mode": "websocket",
                    "expected_nodes": 1,
                    "project_name": "虚拟音频语音闭环测试",
                    "experiment_name": "PC-Pi 音频语音 + 视觉联合闭环",
                    "operator_name": "Codex",
                    "tags": "virtual-pi,voice-audio,vision",
                }
            )
            add_step("session_started", mode=runtime.mode, expected_nodes=runtime.expected_nodes)

            _wait_for(
                lambda: int(runtime.get_state().get("summary", {}).get("online_nodes", 0) or 0) >= 1,
                timeout=20,
                message="虚拟 Pi 节点未上线。",
            )
            add_step("node_online", online_nodes=runtime.get_state().get("summary", {}).get("online_nodes", 0))

            _wait_for(
                lambda: len(server.received_tts) >= 2 and len(server.received_expert_results) >= 1 and len(server.acks) >= 1,
                timeout=40,
                message="音频语音或视觉闭环未完成。",
            )
            add_step(
                "closed_loop_completed",
                tts_count=len(server.received_tts),
                expert_result_count=len(server.received_expert_results),
                ack_count=len(server.acks),
                voice_command_count=len(server.sent_voice_commands),
            )

            runtime.stop_session()
            add_step("session_stopped", phase=runtime.get_state().get("session", {}).get("phase", "unknown"))

        report["server"] = {
            "endpoint": server.endpoint(),
            "sent_voice_commands": list(server.sent_voice_commands),
            "audio_records": list(server.audio_records),
            "audio_suite": dict(server.audio_suite),
            "sent_events": list(server.sent_events),
            "received_tts": list(server.received_tts),
            "received_expert_results": list(server.received_expert_results),
            "acks": list(server.acks),
            "received_commands": list(server.received_commands),
        }
        if runtime is not None:
            report["runtime_state"] = runtime.get_state()
        report["success"] = True
        report["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        return report
    except Exception as exc:
        report["errors"].append(str(exc))
        report["server"] = {
            "endpoint": server.endpoint(),
            "sent_voice_commands": list(server.sent_voice_commands),
            "audio_records": list(server.audio_records),
            "audio_suite": dict(server.audio_suite),
            "sent_events": list(server.sent_events),
            "received_tts": list(server.received_tts),
            "received_expert_results": list(server.received_expert_results),
            "acks": list(server.acks),
            "received_commands": list(server.received_commands),
            "error": str(server.error or ""),
        }
        if runtime is not None:
            report["runtime_state"] = runtime.get_state()
        report["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        return report
    finally:
        if runtime is not None:
            try:
                runtime.shutdown()
            except Exception:
                pass
        server.stop()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    args = _parse_args()
    report = run_virtual_text_voice_closed_loop_test(args.report_file)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
