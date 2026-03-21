#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Web runtime for the NeuroLab Hub dashboard."""

from __future__ import annotations

import asyncio
import io
import importlib
import importlib.util
import json
import os
import queue
import runpy
import subprocess
import sys
import threading
import time
from collections import deque
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any, Callable, Deque, Dict, List, Optional

import cv2
import numpy as np
import websockets

try:
    from PIL import Image, ImageDraw, ImageFont
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

from pc.app_identity import resource_path
from pc.core.subprocess_utils import popen_hidden, run_hidden
from pc.core import logger as core_logger
from pc.core.ai_backend import (
    configured_model_catalog,
    default_model_for_backend,
    get_backend_runtime_config,
    provider_choices,
    save_backend_runtime_config,
    service_provider_keys,
    set_ai_backend,
)
from pc.core.config import get_config, set_config
from pc.core.experiment_archive import get_experiment_archive
from pc.training import training_manager
from pc.training.runtime_env import (
    build_training_python_env,
    describe_training_python,
    install_target_for_training_packages,
    probe_modules_with_training_python,
    resolve_training_python_executable,
)
from pc.core.expert_manager import expert_manager
from pc.core.expert_closed_loop import (
    ExpertResult,
    build_expert_result_command,
    parse_pi_expert_ack,
    parse_pi_expert_packet,
)
from pc.tools.model_downloader import check_and_download_vosk
from pc.tools.model_downloader import check_and_download_sensevoice
from pc.tools.gpu_runtime_helper import detect_gpu_environment, install_cuda_enabled_pytorch
from pc.tools.version_manager import get_app_version
from pc.knowledge_base.rag_engine import knowledge_manager

FONT_CANDIDATES = ["msyh.ttc", "simhei.ttf", "simsun.ttc", "Arial.ttf"]
BASE_DEPENDENCY_MAP = {
    "numpy": "numpy",
    "cv2": "opencv-python",
    "PIL": "pillow",
    "requests": "requests",
    "websockets": "websockets",
    "speech_recognition": "SpeechRecognition",
    "pyaudio": "pyaudio",
    "vosk": "vosk",
    "pyttsx3": "pyttsx3",
}
OPTIONAL_DEPENDENCY_MAP = {
    "torch": "torch",
    "easyocr": "easyocr",
    "mediapipe": "mediapipe",
    "langchain_community": "langchain-community",
    "langchain_huggingface": "langchain-huggingface",
    "sentence_transformers": "sentence-transformers",
    "faiss": "faiss-cpu",
    "transformers": "transformers",
    "accelerate": "accelerate",
    "datasets": "datasets",
    "peft": "peft",
    "ultralytics": "ultralytics",
}
TRAINING_DEPENDENCY_MAP = {
    "torch": "torch",
    "transformers": "transformers",
    "accelerate": "accelerate",
    "datasets": "datasets",
    "peft": "peft",
    "ultralytics": "ultralytics",
}
VOICE_AI_DEPENDENCY_MAP = {
    "funasr": "funasr",
    "modelscope": "modelscope",
    "onnxruntime": "onnxruntime",
    "soundfile": "soundfile",
    "torch": "torch",
    "torchaudio": "torchaudio",
    "openwakeword": "openwakeword",
}


def _now_text() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


class DashboardMultiPiManager:
    def __init__(
        self,
        pi_dict: Dict[str, str],
        log_info: Callable[[str], None],
        log_error: Callable[[str], None],
        selected_model: str = "",
        archive_event: Optional[Callable[..., Any]] = None,
    ) -> None:
        from pc.communication.multi_ws_manager import MultiPiManager as BaseMultiPiManager

        self._base = BaseMultiPiManager(pi_dict)
        self.pi_dict = self._base.pi_dict
        self.frame_buffers = self._base.frame_buffers
        self.send_queues = self._base.send_queues
        self.running = self._base.running
        self.node_status = self._base.node_status
        self.node_caps = self._base.node_caps
        self.target_fps = self._base.target_fps
        self.recent_event_ids = self._base.recent_event_ids
        self.recent_event_queue = self._base.recent_event_queue
        self.pending_result_acks = self._base.pending_result_acks
        self.ack_timeout = self._base.ack_timeout
        self.ack_retries = self._base.ack_retries
        self.event_queue = self._base.event_queue
        self.event_worker_count = self._base.event_worker_count
        self.event_cooldown = self._base.event_cooldown
        self.recent_policy_hits = self._base.recent_policy_hits
        self.audit_log_dir = self._base.audit_log_dir
        self._write_audit = self._base._write_audit
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.log_info = log_info
        self.log_error = log_error
        self.selected_model = str(selected_model or "").strip()
        self.archive_event = archive_event
        self.node_latest_results: Dict[str, Dict[str, Any]] = {
            pid: {"text": "", "event_name": "", "timestamp": 0.0}
            for pid in pi_dict
        }

    async def _send_with_ack(self, ws: Any, pi_id: str, result: ExpertResult) -> bool:
        cmd = build_expert_result_command(result)
        for _ in range(self.ack_retries + 1):
            self.pending_result_acks[(pi_id, result.event_id)] = time.time()
            await self.send_queues[pi_id].put(cmd)
            await asyncio.sleep(self.ack_timeout)
            if (pi_id, result.event_id) not in self.pending_result_acks:
                return True
        return False

    async def _dispatch_expert_result(self, pi_id: str, event_name: str, result: ExpertResult) -> None:
        if not self.running or self.node_status.get(pi_id) != "online":
            return
        acked = await self._send_with_ack(None, pi_id, result)
        self._write_audit(
            f"node={pi_id} event={event_name} event_id={result.event_id} acked={acked} text={result.text}"
        )
        if not acked:
            self.log_error(f"节点 [{pi_id}] 对专家结论未确认 ACK: {result.event_id}")

    def _should_skip_event(self, pi_id: str, event: Any) -> bool:
        expert_code = str(event.expert_code or "").strip() or "|".join(expert_manager.closed_loop_codes_for_event(event.event_name))
        key = (str(pi_id), expert_code or str(event.event_name or "").strip())
        now = time.time()
        last_ts = float(self.recent_policy_hits.get(key, 0.0) or 0.0)
        if now - last_ts < self.event_cooldown:
            return True
        self.recent_policy_hits[key] = now
        return False

    async def _enqueue_edge_event(self, pi_id: str, event: Any) -> None:
        if self._should_skip_event(pi_id, event):
            self.log_info(f"节点 [{pi_id}] 同类策略事件冷却中，已跳过: {event.event_name}")
            return
        try:
            self.event_queue.put_nowait((pi_id, event))
        except asyncio.QueueFull:
            self.log_error(f"节点 [{pi_id}] 边缘事件队列已满，已丢弃: {event.event_name}")

    async def _event_worker(self) -> None:
        from pc.voice.voice_interaction import get_voice_interaction

        while self.running or not self.event_queue.empty():
            try:
                pi_id, event = await asyncio.wait_for(self.event_queue.get(), timeout=0.5)
            except asyncio.TimeoutError:
                continue
            try:
                self.log_info(f"收到节点 [{pi_id}] 边缘高优告警: {event.event_name} ({event.event_id})")
                agent = get_voice_interaction()
                if agent and agent.is_active:
                    self.log_info("语音助手正在活跃，安防播报暂缓")
                    continue

                allowed_codes = []
                if event.expert_code:
                    allowed_codes = [event.expert_code]
                else:
                    allowed_codes = expert_manager.closed_loop_codes_for_event(event.event_name)

                context = {
                    "event_desc": event.event_name,
                    "detected_classes": event.detected_classes,
                    "metrics": event.capture_metrics,
                    "expert_code": event.expert_code,
                    "policy_name": event.policy_name,
                    "policy_action": event.policy_action,
                    "closed_loop_llm": True,
                    "source": "pi_websocket",
                    "model": self.selected_model,
                }
                tts_text = await asyncio.to_thread(
                    expert_manager.route_and_analyze,
                    event.event_name,
                    event.frame,
                    context,
                    allowed_expert_codes=allowed_codes,
                    trigger_mode=None if allowed_codes else "resident",
                )
                if tts_text:
                    self.node_latest_results[pi_id] = {
                        "text": tts_text,
                        "event_name": event.event_name,
                        "timestamp": time.time(),
                    }
                    if self.archive_event is not None:
                        try:
                            self.archive_event(
                                "expert_result",
                                {
                                    "node_id": pi_id,
                                    "event_id": event.event_id,
                                    "event_name": event.event_name,
                                    "result_text": tts_text,
                                },
                                title=f"专家结论 {event.event_name}",
                            )
                        except Exception:
                            pass
                    result = ExpertResult(
                        event_id=event.event_id,
                        text=tts_text,
                        severity="warning",
                        speak=self.node_caps.get(pi_id, {}).get("has_speaker", False),
                    )
                    await self._dispatch_expert_result(pi_id, event.event_name, result)
            except Exception as exc:
                self.log_error(f"节点 [{pi_id}] 边缘事件处理失败: {exc}")
            finally:
                self.event_queue.task_done()

    async def _node_handler(self, pi_id: str, ip: str) -> None:
        from pc.core.expert_manager import expert_manager
        from pc.voice.voice_interaction import get_voice_interaction

        endpoint = str(ip).strip()
        if endpoint.startswith("ws://") or endpoint.startswith("wss://"):
            uri = endpoint
        elif ":" in endpoint:
            uri = f"ws://{endpoint}"
        else:
            uri = f"ws://{endpoint}:8001"
        while self.running:
            try:
                self.node_status[pi_id] = "connecting"
                async with websockets.connect(uri, ping_interval=None) as ws:
                    self.node_status[pi_id] = "online"
                    self.log_info(f"节点 [{pi_id}] ({ip}) 握手成功")
                    await self.send_queues[pi_id].put(f"CMD:SET_FPS:{self.target_fps}")

                    sync_data = {"wake_word": get_config("voice_interaction.wake_word", "小爱同学")}
                    await self.send_queues[pi_id].put(f"CMD:SYNC_CONFIG:{json.dumps(sync_data, ensure_ascii=False)}")

                    policies = expert_manager.get_aggregated_edge_policy()
                    await self.send_queues[pi_id].put(f"CMD:SYNC_POLICY:{json.dumps(policies, ensure_ascii=False)}")
                    self.log_info(f"已向节点 [{pi_id}] 下发 {len(policies['event_policies'])} 条专家策略")

                    async def recv_stream_task() -> None:
                        async for data in ws:
                            if not self.running:
                                break
                            if isinstance(data, str):
                                if data.startswith("PI_VOICE_COMMAND:"):
                                    self._handle_remote_voice(pi_id, data)
                                elif data.startswith("PI_CAPS:"):
                                    caps_raw = data.replace("PI_CAPS:", "", 1)
                                    try:
                                        self.node_caps[pi_id] = json.loads(caps_raw)
                                        self.log_info(f"节点 [{pi_id}] 能力上报: {self.node_caps[pi_id]}")
                                    except Exception:
                                        self.log_error(f"节点 [{pi_id}] 能力上报解析失败")
                                elif data.startswith("PI_EXPERT_ACK:"):
                                    ack, ack_err = parse_pi_expert_ack(data)
                                    if ack_err or not ack:
                                        self.log_error(f"专家回传 ACK 解析失败: {ack_err}")
                                        continue
                                    ack_event_id = str(ack.get("event_id", ""))
                                    self.pending_result_acks.pop((pi_id, ack_event_id), None)
                                    self._write_audit(f"node={pi_id} event_id={ack_event_id} ack={ack}")
                                elif data.startswith("PI_EXPERT_EVENT:") or data.startswith("PI_YOLO_EVENT:"):
                                    event, parse_error = parse_pi_expert_packet(data)
                                    if parse_error or event is None:
                                        self.log_error(f"处理边缘告警事件异常: {parse_error}")
                                        continue
                                    if event.event_id in self.recent_event_ids:
                                        self.log_info(f"节点 [{pi_id}] 重复事件已忽略: {event.event_id}")
                                        continue
                                    self.recent_event_ids.add(event.event_id)
                                    self.recent_event_queue.append(event.event_id)
                                    while len(self.recent_event_ids) > self.recent_event_queue.maxlen:
                                        expired = self.recent_event_queue.popleft()
                                        self.recent_event_ids.discard(expired)

                                    await self._enqueue_edge_event(pi_id, event)
                                    continue

                                    self.log_info(f"收到节点 [{pi_id}] 边缘高优告警: {event.event_name} ({event.event_id})")
                                    agent = get_voice_interaction()
                                    if agent and agent.is_active:
                                        self.log_info("语音助手正在活跃，安防播报暂缓")
                                        continue

                                    allowed_codes = []
                                    if event.expert_code:
                                        allowed_codes = [event.expert_code]
                                    else:
                                        allowed_codes = expert_manager.closed_loop_codes_for_event(event.event_name)

                                    context = {
                                        "event_desc": event.event_name,
                                        "detected_classes": event.detected_classes,
                                        "metrics": event.capture_metrics,
                                        "expert_code": event.expert_code,
                                        "policy_name": event.policy_name,
                                        "policy_action": event.policy_action,
                                        "closed_loop_llm": True,
                                        "source": "pi_websocket",
                                        "model": self.selected_model,
                                    }
                                    tts_text = await asyncio.to_thread(
                                        expert_manager.route_and_analyze,
                                        event.event_name,
                                        event.frame,
                                        context,
                                        allowed_expert_codes=allowed_codes,
                                        trigger_mode=None if allowed_codes else "resident",
                                    )
                                    if tts_text:
                                        self.node_latest_results[pi_id] = {
                                            "text": tts_text,
                                            "event_name": event.event_name,
                                            "timestamp": time.time(),
                                        }
                                        if self.archive_event is not None:
                                            try:
                                                self.archive_event(
                                                    "expert_result",
                                                    {
                                                        "node_id": pi_id,
                                                        "event_id": event.event_id,
                                                        "event_name": event.event_name,
                                                        "result_text": tts_text,
                                                    },
                                                    title=f"专家结论 {event.event_name}",
                                                )
                                            except Exception:
                                                pass
                                        result = ExpertResult(
                                            event_id=event.event_id,
                                            text=tts_text,
                                            severity="warning",
                                            speak=self.node_caps.get(pi_id, {}).get("has_speaker", False),
                                        )
                                        asyncio.create_task(self._dispatch_expert_result(ws, pi_id, event.event_name, result)); acked = True
                                        self._write_audit(
                                            f"node={pi_id} event={event.event_name} event_id={event.event_id} acked={acked} text={tts_text}"
                                        )
                                        if not acked:
                                            self.log_error(f"节点 [{pi_id}] 对专家结论未确认 ACK: {event.event_id}")
                                continue

                            arr = np.frombuffer(data, np.uint8)
                            frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                            if frame is not None:
                                self.frame_buffers[pi_id] = frame

                    async def send_command_task() -> None:
                        while self.running:
                            msg = await self.send_queues[pi_id].get()
                            await ws.send(msg)

                    await asyncio.gather(recv_stream_task(), send_command_task())
            except Exception as exc:
                if self.running:
                    self.node_status[pi_id] = "offline"
                    self.log_error(f"节点 [{pi_id}] ({ip}) 通信中断，5 秒后重连: {exc}")
                    await asyncio.sleep(5)

    def _handle_remote_voice(self, pi_id: str, data: str) -> None:
        from pc.voice.voice_interaction import get_voice_interaction

        cmd_text = data.replace("PI_VOICE_COMMAND:", "", 1).strip()
        self.log_info(f"收到节点 {pi_id} 语音指令: {cmd_text}")
        agent = get_voice_interaction()
        if not agent:
            self.send_to_node(pi_id, "CMD:TTS:语音助手未就绪，请先检查 PC 端依赖。")
            return

        def _reply(answer: str) -> None:
            message = str(answer or "").strip()
            if not message:
                return
            self.node_latest_results[pi_id] = {
                "text": message,
                "event_name": "语音交互",
                "timestamp": time.time(),
            }
            preview = message if len(message) <= 120 else f"{message[:117]}..."
            self.log_info(f"已回传节点 {pi_id} 语音播报: {preview}")
            self._write_audit(f"node={pi_id} voice_command={cmd_text} reply={message}")
            self.send_to_node(pi_id, f"CMD:TTS:{message}")

        threading.Thread(
            target=agent.process_remote_command,
            args=(pi_id, cmd_text, _reply),
            daemon=True,
            name=f"PiVoiceRoute_{pi_id}",
        ).start()

    async def start(self) -> None:
        self.loop = asyncio.get_running_loop()
        self.running = True
        self._base.running = True
        tasks = [self._node_handler(pid, ip) for pid, ip in self.pi_dict.items()]
        tasks.extend(self._event_worker() for _ in range(self.event_worker_count))
        await asyncio.gather(*tasks)

    def send_to_node(self, pi_id: str, text: str) -> None:
        queue_ref = self.send_queues.get(pi_id)
        if queue_ref is None:
            return
        if self.loop is not None and self.loop.is_running():
            self.loop.call_soon_threadsafe(queue_ref.put_nowait, text)
        else:
            queue_ref.put_nowait(text)

    def stop(self) -> None:
        self.running = False
        self._base.running = False
        self.pending_result_acks.clear()
        self.recent_policy_hits.clear()
        while not self.event_queue.empty():
            try:
                self.event_queue.get_nowait()
                self.event_queue.task_done()
            except Exception:
                break


class LabDetectorRuntime:
    def __init__(self) -> None:
        self.version = get_app_version()
        self.lock = threading.RLock()
        self.logs: Deque[Dict[str, str]] = deque(maxlen=240)
        self.self_check_results: List[Dict[str, Any]] = []
        self.ai_backend = str(get_config("ai_backend.type", "ollama"))
        self.selected_model = self._default_model_for(self.ai_backend)
        self.mode = "idle"
        self.expected_nodes = 1
        self.status_message = "等待配置"
        self.session_active = False
        self.session_phase = "idle"
        self.started_at = 0.0
        self.server_meta = {"host": "127.0.0.1", "port": 8765}

        self.local_frame: Optional[np.ndarray] = None
        self.latest_inference_result: Dict[str, Any] = {"text": "", "timestamp": 0.0}
        self.last_inference_log_ts = 0.0
        self.inference_queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=1)

        self.capture: Optional[cv2.VideoCapture] = None
        self.camera_thread: Optional[threading.Thread] = None
        self.inference_thread: Optional[threading.Thread] = None
        self.manager_thread: Optional[threading.Thread] = None
        self.background_init_thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()

        self.topology: Dict[str, str] = {}
        self.manager: Optional[DashboardMultiPiManager] = None
        self.voice_agent: Any = None
        self.scheduler_started = False
        self._scheduler_manager: Any = None
        self.self_check_has_run = False
        self.demo_mode_enabled = False
        self.demo_interval = 8.0
        self.demo_thread: Optional[threading.Thread] = None
        self.demo_sequence: List[Dict[str, Any]] = []
        self.demo_index = 0
        self._refresh_shadow_demo_config()
        self.experiment_archive = get_experiment_archive()
        self.session_metadata: Dict[str, Any] = {}
        self.archive_session_id = ""

    def set_server_meta(self, host: str, port: int) -> None:
        self.server_meta = {"host": host, "port": port}

    def _log(self, level: str, text: str) -> None:
        self.logs.append({"timestamp": _now_text(), "level": level, "text": text})
        try:
            if level == "ERROR":
                core_logger.console_error(text)
            elif level == "PROMPT":
                core_logger.console_prompt(text)
            else:
                core_logger.console_info(text)
        except Exception:
            pass

    def _log_info(self, text: str) -> None:
        self._log("INFO", text)

    def _log_error(self, text: str) -> None:
        self._log("ERROR", text)

    def _log_raw_line(self, raw: str, level: str = "INFO") -> None:
        if raw is None:
            return
        line = str(raw).rstrip("\r\n")
        self.logs.append({
            "timestamp": _now_text(),
            "level": level,
            "text": line,
            "rendered": line,
        })
        try:
            stream = sys.stdout or sys.__stdout__
            if stream is not None:
                print(line, file=stream)
        except Exception:
            pass

    def _reset_logs(self) -> None:
        self.logs.clear()

    def _default_model_for(self, backend: str) -> str:
        if backend == "ollama":
            models = self._ollama_models()
            return models[0] if models else default_model_for_backend(backend)
        return default_model_for_backend(backend)

    def _refresh_shadow_demo_config(self) -> None:
        self.demo_mode_enabled = bool(get_config("shadow_demo.enabled", False))
        try:
            interval = float(get_config("shadow_demo.interval_seconds", 8))
        except (TypeError, ValueError):
            interval = 8.0
        self.demo_interval = max(4.0, interval)

    def _ollama_models(self) -> List[str]:
        models = configured_model_catalog().get("ollama", [])
        return list(models)

    def refresh_model_catalog(self) -> Dict[str, List[str]]:
        return configured_model_catalog()

    def bootstrap(self, include_self_check: bool = True, include_catalogs: bool = True) -> Dict[str, Any]:
        if include_self_check and not self.self_check_has_run:
            self.run_self_check()
        catalog = self.refresh_model_catalog()
        payload = {
            "version": self.version,
            "server": self.server_meta,
            "controls": {
                "backends": provider_choices(),
                "modes": [
                    {"value": "camera", "label": "单机摄像头模式"},
                    {"value": "websocket", "label": "多节点 WebSocket 模式"},
                ],
                "models": catalog,
                "defaults": {
                    "ai_backend": self.ai_backend,
                    "selected_model": self.selected_model,
                    "mode": "camera",
                    "expected_nodes": 1,
                    "project_name": str(get_config("session_defaults.project_name", "AI4S 实验项目")),
                    "experiment_name": str(get_config("session_defaults.experiment_name", "桌面监控实验")),
                    "operator_name": str(get_config("session_defaults.operator_name", "")),
                    "tags": str(get_config("session_defaults.tags", "桌面端,监控,AI4S")),
                },
            },
            "state": self.get_state(),
        }
        if include_catalogs:
            payload["knowledge_bases"] = self.get_knowledge_base_catalog()
            payload["experts"] = self.get_expert_catalog()
            payload["cloud_backends"] = self.get_cloud_backend_catalog()
            payload["training"] = self.get_training_overview()
        return payload

    def get_state(self) -> Dict[str, Any]:
        streams = self._build_streams()
        summary = {
            "session_active": self.session_active,
            "online_nodes": sum(1 for item in streams if item["status"] == "online"),
            "offline_nodes": sum(1 for item in streams if item["status"] == "offline"),
            "stream_count": len(streams),
            "voice_running": bool(self.voice_agent and getattr(self.voice_agent, "is_running", False)),
        }
        return {
            "version": self.version,
            "session": {
                "active": self.session_active,
                "phase": self.session_phase,
                "mode": self.mode,
                "ai_backend": self.ai_backend,
                "selected_model": self.selected_model,
                "expected_nodes": self.expected_nodes,
                "started_at": self.started_at,
                "status_message": self.status_message,
                "archive_session_id": self.archive_session_id,
                "metadata": dict(self.session_metadata),
            },
            "summary": summary,
            "self_check": self.self_check_results,
            "streams": streams,
            "logs": list(self.logs),
        }

    def get_streams_state(self) -> Dict[str, Any]:
        return {
            "session": {
                "active": self.session_active,
                "phase": self.session_phase,
                "mode": self.mode,
                "status_message": self.status_message,
            },
            "streams": self._build_streams(),
        }

    def run_self_check(
        self,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        *,
        include_microphone: bool = False,
    ) -> List[Dict[str, Any]]:
        checks = [
            ("dependencies", "Python 依赖环境", self._check_dependencies),
            ("gpu", "GPU 算力环境", self._check_gpu),
            ("training_runtime", "训练运行时环境", self._check_training_runtime),
            ("voice_ai_runtime", "增强语音识别运行时", self._check_voice_ai_runtime),
            ("sensevoice", "SenseVoice 模型资产", self._check_sensevoice_assets),
            ("vosk", "离线语音模型资产", self._check_vosk_assets),
            ("rag", "实验室知识库目录 (RAG)", self._check_rag_assets),
        ]
        if include_microphone:
            checks.append(("microphone", "PC 麦克风与语音链路", self._check_microphone))

        total_checks = len(checks)
        results: List[Dict[str, Any]] = []
        self._log_raw_line("")
        self._log_raw_line("=" * 55)
        self._log_raw_line(f"[INFO] NeuroLab Hub V{self.version} (PC 智算中枢) - 系统启动自检")
        self._log_raw_line("=" * 55)

        for index, (key, title, runner) in enumerate(checks, start=1):
            if progress_callback is not None:
                progress_callback({
                    "value": 18 + ((index - 1) / max(total_checks, 1)) * 58,
                    "message": f"正在执行启动自检（{index}/{total_checks}）",
                    "step": title,
                    "detail": f"检查项：{title}",
                })
            self._log_raw_line("")
            self._log_raw_line(f"[INFO] [{index}/{total_checks}] 检查 {title}...")
            start_time = time.time()
            try:
                result = runner()
            except Exception as exc:
                result = {
                    "status": "error",
                    "summary": f"{title} 检查失败",
                    "detail": str(exc),
                    "raw_output": str(exc),
                }
            raw_output = str(result.get("raw_output") or "")
            for line in raw_output.splitlines():
                self._log_raw_line(line)
            result.update({
                "key": key,
                "title": title,
                "duration_ms": int((time.time() - start_time) * 1000),
            })
            results.append(result)
            if progress_callback is not None:
                progress_callback({
                    "value": 18 + (index / max(total_checks, 1)) * 58,
                    "message": f"启动自检已完成 {index}/{total_checks}",
                    "step": title,
                    "detail": f"{title}：{result.get('summary', '')}",
                })

        has_error = any(str(row.get("status", "")).lower() == "error" for row in results)
        has_warn = any(str(row.get("status", "")).lower() == "warn" for row in results)
        self._log_raw_line("")
        self._log_raw_line("=" * 55)
        if has_error:
            self._log_raw_line("[ERROR] 系统自检存在失败项，请先处理后再启动。")
        elif has_warn:
            self._log_raw_line("[WARN] 系统自检完成，存在告警项，可继续使用并按需补齐能力。")
        else:
            self._log_raw_line("[INFO] 系统自检全部通过，正在启动主控制流...")
        self._log_raw_line("=" * 55)
        self._log_raw_line("")
        self.self_check_results = results
        self.self_check_has_run = True
        return results

    def run_voice_test(self) -> Dict[str, Any]:
        self._log_info("开始执行本地语音测试")

        mic_result = self._check_microphone()
        raw_output = str(mic_result.get("raw_output") or "").strip()
        for line in raw_output.splitlines():
            self._log_raw_line(line, level="INFO" if "[ERROR]" not in line else "ERROR")
        if str(mic_result.get("status") or "").lower() == "error":
            return {
                "status": "error",
                "summary": "本地语音测试失败",
                "detail": str(mic_result.get("detail") or mic_result.get("summary") or "麦克风链路不可用。"),
            }

        try:
            import pc.voice.voice_interaction as voice_module

            original_console_info = voice_module.console_info
            original_console_error = voice_module.console_error

            def _voice_info(message: str) -> None:
                text = str(message or "").strip()
                if text:
                    self._log_info(text)

            def _voice_error(message: str) -> None:
                text = str(message or "").strip()
                if text:
                    self._log_error(text)

            voice_module.console_info = _voice_info
            voice_module.console_error = _voice_error

            get_voice_interaction = voice_module.get_voice_interaction
            try:
                agent = get_voice_interaction()
                if agent is None:
                    self._log_error("语音测试未能创建语音助手实例")
                    return {
                        "status": "error",
                        "summary": "本地语音测试失败",
                        "detail": "未能创建语音助手实例，请检查语音依赖是否完整。",
                    }

                wake_word = str(getattr(getattr(agent, "config", None), "wake_word", "") or "").strip()
                self._log_info("正在尝试启动本地语音助手")
                agent.set_ai_backend(self.ai_backend, self.selected_model)
                agent.open_runtime_session(mode="voice_test", source="pc_local", metadata={"test": True})

                started_here = False
                if not getattr(agent, "is_running", False):
                    started_here = bool(agent.start())
                if not getattr(agent, "is_running", False):
                    self._log_error("本地语音助手未能启动，请检查麦克风占用或 Windows 录音权限")
                    return {
                        "status": "warn",
                        "summary": "本地语音链路未完全启动",
                        "detail": "麦克风基础检测已通过，但语音助手未能真正启动。请检查麦克风是否被其他程序占用，以及 Windows 录音权限是否允许 Python/PyCharm 访问。",
                    }

                self._log_info(f"本地语音助手已启动，当前唤醒词：{wake_word or '未配置'}")
                self._log_info(f"请先在 12 秒内说出唤醒词：{wake_word or '未配置'}")

                wake_detected = False
                wake_deadline = time.time() + 12.0
                while time.time() < wake_deadline:
                    if getattr(agent, "is_active", False):
                        wake_detected = True
                        break
                    time.sleep(0.2)

                if not wake_detected:
                    self._log_error("本地语音测试未在限定时间内检测到唤醒词")
                    return {
                        "status": "warn",
                        "summary": "本地语音已启动，但未检测到唤醒词",
                        "detail": f"语音助手已启动，但在 12 秒内没有识别到唤醒词“{wake_word or '未配置'}”。请优先检查麦克风输入音量、环境噪音，以及唤醒词是否与当前配置一致。",
                    }

                self._log_info("本地语音测试已检测到唤醒词")
                self._log_info("请在 15 秒内继续说出一条测试指令，例如“介绍当前系统状态”")

                command_text = ""
                answer_text = ""
                command_deadline = time.time() + 15.0
                while time.time() < command_deadline:
                    for row in reversed(self.logs):
                        text = str(row.get("text") or "")
                        if not command_text and "收到语音输入" in text:
                            command_text = text
                        if not answer_text and "AI 回答" in text:
                            answer_text = text
                        if command_text and answer_text:
                            break
                    if command_text and answer_text:
                        break
                    time.sleep(0.2)

                if command_text and answer_text:
                    playback_wait = max(3.0, min(10.0, len(answer_text) / 10.0))
                    self._log_info(f"等待 {playback_wait:.1f} 秒以完成语音播报")
                    playback_deadline = time.time() + playback_wait
                    while time.time() < playback_deadline:
                        interrupted = False
                        for row in reversed(self.logs):
                            text = str(row.get("text") or "")
                            if "已停止语音播报" in text:
                                interrupted = True
                                break
                        if interrupted:
                            self._log_info("检测到停止播报指令，提前结束等待")
                            break
                        time.sleep(0.2)
                    self._log_info("本地语音测试已完成唤醒、识别和应答")
                    return {
                        "status": "pass",
                        "summary": "本地语音完整链路测试通过",
                        "detail": f"{command_text}\n{answer_text}",
                    }

                if command_text:
                    self._log_error("本地语音已识别到测试指令，但尚未收到 AI 应答")
                    return {
                        "status": "warn",
                        "summary": "已识别到语音指令，但未完成应答",
                        "detail": command_text,
                    }

                self._log_error("本地语音已唤醒，但未识别到后续测试指令")
                return {
                    "status": "warn",
                    "summary": "已检测到唤醒词，但未识别到后续指令",
                    "detail": "语音助手已经进入唤醒状态，但在等待窗口内没有识别到后续指令。请说得更近一些，或适当提高麦克风输入音量。",
                }
            finally:
                try:
                    if 'started_here' in locals() and started_here and agent is not None:
                        agent.stop()
                except Exception:
                    pass
                try:
                    if 'agent' in locals() and agent is not None:
                        agent.close_runtime_session()
                except Exception:
                    pass
                voice_module.console_info = original_console_info
                voice_module.console_error = original_console_error
        except Exception as exc:
            self._log_error(f"本地语音测试异常: {exc}")
            return {
                "status": "error",
                "summary": "本地语音测试失败",
                "detail": str(exc),
            }






    def _check_training_runtime(self) -> Dict[str, Any]:
        python_info = describe_training_python()
        if not python_info.get("available"):
            detail = str(python_info.get("reason") or "Training interpreter not found.")
            return {
                "status": "warn",
                "summary": "Training runtime not ready",
                "detail": detail,
                "raw_output": f"[WARN] {detail}",
            }

        runtime_kind = {
            "bundled": "Bundled runtime",
            "system": "System Python",
            "current": "Current interpreter",
        }.get(str(python_info.get("kind") or ""), "Python")
        runtime_path = str(python_info.get("path") or "")
        return {
            "status": "pass",
            "summary": f"Training interpreter ready ({runtime_kind})",
            "detail": runtime_path or "Interpreter detected",
            "raw_output": "\n".join([
                f"[INFO] Training interpreter: {runtime_path}",
                "[INFO] Training dependencies are checked only when a training job starts.",
            ]),
        }

    @staticmethod
    def _missing_dependencies(module_map: Dict[str, str]) -> List[str]:
        missing: List[str] = []
        for module_name, package_name in module_map.items():
            if importlib.util.find_spec(module_name) is None:
                missing.append(package_name)
        return missing

    def _missing_dependencies_in_training_env(self, module_map: Dict[str, str]) -> tuple[List[str], List[str], Dict[str, Any]]:
        probe = probe_modules_with_training_python(module_map.keys())
        logs = list(probe.get("logs") or [])
        results = dict(probe.get("results") or {})
        missing = [package_name for module_name, package_name in module_map.items() if not results.get(module_name, False)]
        return missing, logs, probe

    def _ensure_pip_available(
        self,
        python_exe: Path | None = None,
        env: Dict[str, str] | None = None,
    ) -> Dict[str, Any]:
        logs: List[str] = []
        target_python = python_exe
        if target_python is None:
            if getattr(sys, "frozen", False):
                resolved = resolve_training_python_executable()
                target_python = Path(resolved) if resolved is not None else None
            else:
                target_python = Path(sys.executable)
        if target_python is None or not Path(target_python).exists():
            return {"ok": False, "logs": ["[ERROR] 未找到可用于自动安装依赖的 Python 解释器。"]}

        runtime_env = env or build_training_python_env(Path(target_python))
        check_cmd = [str(target_python), "-m", "pip", "--version"]
        check = run_hidden(check_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=runtime_env)
        if check.returncode == 0:
            output = self._decode_subprocess_output(check.stdout).strip()
            if output:
                logs.append(f"[INFO] pip 已就绪: {output}")
            return {"ok": True, "logs": logs}

        logs.append("[WARN] pip 不可用，尝试通过 ensurepip 自动补齐。")
        ensure_cmd = [str(target_python), "-m", "ensurepip", "--upgrade"]
        ensure = run_hidden(ensure_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=runtime_env)
        ensure_output = self._decode_subprocess_output(ensure.stdout).strip()
        if ensure_output:
            logs.extend([f"[INFO] {line}" for line in ensure_output.splitlines()[-12:]])

        recheck = run_hidden(check_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=runtime_env)
        if recheck.returncode == 0:
            output = self._decode_subprocess_output(recheck.stdout).strip()
            if output:
                logs.append(f"[INFO] pip 修复成功: {output}")
            return {"ok": True, "logs": logs}

        logs.append("[ERROR] pip 仍不可用，无法自动安装 Python 依赖。")
        return {"ok": False, "logs": logs}

    def _install_python_packages(
        self,
        packages: List[str],
        scope_name: str,
        python_exe: Path | None = None,
        env: Dict[str, str] | None = None,
        install_target: Path | None = None,
    ) -> Dict[str, Any]:
        uniq_packages = sorted({str(pkg).strip() for pkg in packages if str(pkg).strip()})
        if not uniq_packages:
            return {"ok": True, "installed": [], "failed": [], "logs": [f"[INFO] {scope_name} 无需安装。"]}

        target_python = python_exe
        if target_python is None:
            if getattr(sys, "frozen", False):
                resolved = resolve_training_python_executable()
                target_python = Path(resolved) if resolved is not None else None
            else:
                target_python = Path(sys.executable)
        if target_python is None or not Path(target_python).exists():
            return {"ok": False, "installed": [], "failed": uniq_packages, "logs": ["[ERROR] 未找到可执行的 Python 解释器。"]}

        runtime_env = env or build_training_python_env(Path(target_python))
        install_root = install_target
        if install_root is None and getattr(sys, "frozen", False):
            install_root = install_target_for_training_packages()
        logs: List[str] = [f"[INFO] 开始自动安装{scope_name}: {', '.join(uniq_packages)}"]
        if install_root is not None:
            Path(install_root).mkdir(parents=True, exist_ok=True)
            logs.append(f"[INFO] 安装目标目录: {install_root}")
        logs.append(f"[INFO] 安装解释器: {target_python}")

        pip_state = self._ensure_pip_available(Path(target_python), runtime_env)
        logs.extend(pip_state["logs"])
        if not pip_state["ok"]:
            return {"ok": False, "installed": [], "failed": uniq_packages, "logs": logs}

        installed: List[str] = []
        failed: List[str] = []
        for package_name in uniq_packages:
            cmd = [str(target_python), "-m", "pip", "install", "--upgrade", "--no-warn-script-location", package_name]
            if install_root is not None:
                cmd.extend(["--target", str(install_root)])
            proc = run_hidden(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=runtime_env)
            output = self._decode_subprocess_output(proc.stdout)
            tail_lines = [line for line in output.splitlines() if line.strip()][-12:]
            if proc.returncode == 0:
                installed.append(package_name)
                logs.append(f"[INFO] 安装成功: {package_name}")
            else:
                failed.append(package_name)
                logs.append(f"[ERROR] 安装失败: {package_name}")
            logs.extend([f"[INFO] {line}" for line in tail_lines])

        return {
            "ok": len(failed) == 0,
            "installed": installed,
            "failed": failed,
            "logs": logs,
        }

    def _check_dependencies(self) -> Dict[str, Any]:
        auto_install_core = bool(get_config("self_check.pc_auto_install_core", True))
        logs: List[str] = []
        missing_base = self._missing_dependencies(BASE_DEPENDENCY_MAP)

        target_python = resolve_training_python_executable()
        runtime_env = build_training_python_env(Path(target_python)) if target_python else None
        install_target = install_target_for_training_packages()

        if missing_base and auto_install_core:
            install_report = self._install_python_packages(
                missing_base,
                "Core dependencies",
                python_exe=Path(target_python) if target_python else None,
                env=runtime_env,
                install_target=install_target,
            )
            logs.extend(install_report["logs"])

        missing_base = self._missing_dependencies(BASE_DEPENDENCY_MAP)
        installed_base_count = len(BASE_DEPENDENCY_MAP) - len(missing_base)
        logs.append(
            f"[INFO] Core Python dependency check finished: {installed_base_count}/{len(BASE_DEPENDENCY_MAP)} ready."
        )
        logs.append("[INFO] Training dependencies for YOLO and LLM are checked on demand, not during startup self-check.")

        if missing_base:
            return {
                "status": "error",
                "summary": f"Missing {len(missing_base)} core packages",
                "detail": "Missing core dependencies: " + ", ".join(missing_base),
                "raw_output": "\n".join(logs),
            }

        return {
            "status": "pass",
            "summary": f"{installed_base_count} core packages ready",
            "detail": "Desktop runtime imports are available. Training dependencies are checked separately.",
            "raw_output": "\n".join(logs),
        }

    def _check_voice_ai_runtime(self) -> Dict[str, Any]:
        auto_install_voice_ai = bool(get_config("self_check.pc_auto_install_voice_ai", True))
        logs: List[str] = []
        missing_voice_ai = self._missing_dependencies(VOICE_AI_DEPENDENCY_MAP)

        target_python = resolve_training_python_executable()
        runtime_env = build_training_python_env(Path(target_python)) if target_python else None
        install_target = install_target_for_training_packages()

        if missing_voice_ai and auto_install_voice_ai:
            install_report = self._install_python_packages(
                missing_voice_ai,
                "Voice AI dependencies",
                python_exe=Path(target_python) if target_python else None,
                env=runtime_env,
                install_target=install_target,
            )
            logs.extend(install_report["logs"])

        missing_voice_ai = self._missing_dependencies(VOICE_AI_DEPENDENCY_MAP)
        ready_count = len(VOICE_AI_DEPENDENCY_MAP) - len(missing_voice_ai)
        logs.append(
            f"[INFO] Voice AI dependency check finished: {ready_count}/{len(VOICE_AI_DEPENDENCY_MAP)} ready."
        )

        if missing_voice_ai:
            return {
                "status": "warn",
                "summary": f"Voice AI 缺少 {len(missing_voice_ai)} 项依赖",
                "detail": "Missing voice AI dependencies: " + ", ".join(missing_voice_ai),
                "raw_output": "\n".join(logs),
            }

        return {
            "status": "pass",
            "summary": "增强语音识别运行时已就绪",
            "detail": "FunASR / SenseVoice 运行时依赖可用。",
            "raw_output": "\n".join(logs),
        }

    def _ensure_training_dependencies_ready(self) -> None:
        self._log_raw_line("[INFO] Checking training dependencies on demand before starting the job.")
        missing_training, probe_logs, probe = self._missing_dependencies_in_training_env(TRAINING_DEPENDENCY_MAP)
        for line in probe_logs:
            self._log_raw_line(line)
        if not missing_training:
            return

        python_info = describe_training_python()
        if not python_info.get("available"):
            raise RuntimeError(str(python_info.get("reason") or "未找到训练运行时 Python。"))

        auto_install_training = bool(get_config("self_check.pc_auto_install_training", True))
        if auto_install_training:
            target_python = resolve_training_python_executable()
            install_report = self._install_python_packages(
                missing_training,
                "训练依赖",
                python_exe=Path(target_python) if target_python else None,
                env=build_training_python_env(Path(target_python)) if target_python else None,
                install_target=install_target_for_training_packages(),
            )
            for line in install_report["logs"]:
                self._log_raw_line(line)
            missing_training, _, _ = self._missing_dependencies_in_training_env(TRAINING_DEPENDENCY_MAP)

        if missing_training:
            raise RuntimeError("训练依赖未就绪: " + ", ".join(missing_training) + "。请先运行启动自检。")

    def _decode_subprocess_output(self, payload: bytes) -> str:
        for encoding in ("utf-8", "gbk", "cp936"):
            try:
                return payload.decode(encoding)
            except Exception:
                continue
        return payload.decode("utf-8", errors="ignore")

    def _run_python_script(self, relative_path: str) -> str:
        module_name = relative_path.replace("\\", "/").removesuffix(".py").replace("/", ".")
        resource_file = resource_path(relative_path)
        buffer = io.StringIO()
        try:
            with redirect_stdout(buffer), redirect_stderr(buffer):
                if module_name.startswith("pc."):
                    runpy.run_module(module_name, run_name="__main__")
                else:
                    runpy.run_path(str(resource_file), run_name="__main__")
        except SystemExit:
            pass
        except Exception as exc:
            output = buffer.getvalue().strip()
            error_text = f"[ERROR] \u811a\u672c\u6267\u884c\u5931\u8d25: {exc}"
            return f"{output}\n{error_text}".strip() if output else error_text
        return buffer.getvalue().strip()

    def _check_gpu(self) -> Dict[str, Any]:
        output = self._run_python_script("pc/tools/check_gpu.py")
        status = "pass" if "GPU 可用: True" in output else "warn"
        summary = "检测到可用 GPU" if status == "pass" else "未检测到 CUDA，可降级到 CPU"
        return {
            "status": status,
            "summary": summary,
            "detail": output or "未返回输出",
            "raw_output": output or "[WARN] GPU 检查脚本未返回输出",
        }

    def _check_gpu(self) -> Dict[str, Any]:
        report = detect_gpu_environment()
        details = dict(report.get("details") or {})
        logs = list(report.get("logs") or [])

        auto_install = bool(get_config("self_check.pc_auto_install_gpu_runtime", True))
        auto_install_on_nvidia = bool(get_config("gpu_runtime.auto_install_on_nvidia", True))
        cuda_packages_raw = str(get_config("gpu_runtime.pytorch_cuda_packages", "torch,torchvision,torchaudio"))
        cuda_packages = [item.strip() for item in cuda_packages_raw.split(",") if item.strip()]
        index_url = str(get_config("gpu_runtime.pytorch_cuda_index_url", "https://download.pytorch.org/whl/cu124")).strip()

        if details.get("can_auto_install_cuda_torch") and auto_install and auto_install_on_nvidia:
            logs.append("[INFO] 检测到 NVIDIA GPU，但当前 PyTorch 仍为 CPU 运行时，开始自动补齐 CUDA 版 PyTorch。")
            install_report = install_cuda_enabled_pytorch(index_url, cuda_packages)
            logs.append(f"[INFO] 安装命令: {install_report.get('command', '')}")
            for line in list(install_report.get("logs") or []):
                logs.append(f"[INFO] {line}")
            if install_report.get("ok"):
                logs.append("[INFO] CUDA 版 PyTorch 安装完成，正在重新检测 GPU 状态。")
                report = detect_gpu_environment()
                details = dict(report.get("details") or {})
                logs.extend(list(report.get("logs") or []))
            else:
                logs.append("[WARN] CUDA 版 PyTorch 自动安装未完成，将继续使用 CPU。")

        if details.get("torch_cuda_available"):
            status = "pass"
            summary = "检测到可用 GPU"
            detail = details.get("nvidia_gpu_name") or "CUDA 运行时可用"
        elif details.get("needs_cuda_torch"):
            status = "warn"
            summary = "检测到 NVIDIA GPU，但仍在使用 CPU 版 PyTorch"
            detail = (
                f"NVIDIA GPU: {details.get('nvidia_gpu_name') or '未知'}；"
                "可在联网环境下自动安装 CUDA 版 PyTorch，或手动执行官方安装命令。"
            )
            logs.append(f"[INFO] 建议使用官方 PyTorch CUDA 源: {index_url}")
        elif details.get("needs_driver"):
            status = "warn"
            summary = "未检测到可用 CUDA，将继续使用 CPU"
            detail = "当前环境未发现可用 NVIDIA 驱动或 GPU。若设备支持 NVIDIA GPU，请先安装官方驱动。"
        else:
            status = "warn"
            summary = "未检测到可用 CUDA，将继续使用 CPU"
            detail = "当前环境未发现可用 GPU / CUDA 运行时。"

        return {
            "status": status,
            "summary": summary,
            "detail": detail,
            "raw_output": "\n".join(logs) if logs else "[WARN] GPU 检查未返回输出",
        }

    def _check_microphone(self) -> Dict[str, Any]:
        output = self._run_python_script("pc/tools/check_mic.py")
        if "[ERROR]" in output:
            status = "error"
            summary = "麦克风检查失败"
        elif "[WARN]" in output:
            status = "warn"
            summary = "麦克风可用性存在风险"
        else:
            status = "pass"
            summary = "麦克风链路可用"
        return {
            "status": status,
            "summary": summary,
            "detail": output or "未返回输出",
            "raw_output": output or "[WARN] 麦克风检查脚本未返回输出",
        }

    def _check_vosk_assets(self) -> Dict[str, Any]:
        model_root = Path(resource_path("pc/voice/model"))
        model_am = model_root / "am"
        if model_am.exists():
            return {
                "status": "pass",
                "summary": "离线语音模型已就绪",
                "detail": str(model_root),
                "raw_output": f"[INFO] 已检测到 Vosk 离线语音模型目录: {model_root}",
            }

        buffer = io.StringIO()
        result_holder: Dict[str, Any] = {"ready": False, "error": ""}

        def worker() -> None:
            try:
                with redirect_stdout(buffer), redirect_stderr(buffer):
                    result_holder["ready"] = check_and_download_vosk()
            except Exception as exc:
                result_holder["error"] = str(exc)

        thread = threading.Thread(target=worker, daemon=True, name="VoskAssetCheck")
        thread.start()
        thread.join(20)

        output = buffer.getvalue().strip()
        if thread.is_alive():
            timeout_text = "[WARN] Vosk 离线语音模型自动补齐超时，已跳过本次下载。"
            output = f"{output}\n{timeout_text}" if output else timeout_text
            return {
                "status": "warn",
                "summary": "离线语音模型尚未就绪",
                "detail": str(model_root),
                "raw_output": output,
            }

        if result_holder["error"]:
            output = f"{output}\n[ERROR] {result_holder['error']}" if output else f"[ERROR] {result_holder['error']}"
            return {
                "status": "error",
                "summary": "离线语音模型补齐失败",
                "detail": str(model_root),
                "raw_output": output,
            }

        if not output:
            output = "[INFO] 已自动完成离线语音模型资产检查."
        return {
            "status": "pass" if result_holder["ready"] else "warn",
            "summary": "已自动补齐离线语音模型" if result_holder["ready"] else "离线语音模型尚未就绪",
            "detail": str(model_root),
            "raw_output": output,
        }

    def _check_sensevoice_assets(self) -> Dict[str, Any]:
        model_root = Path(resource_path("pc/voice/models/SenseVoiceSmall"))
        config_file = model_root / "configuration.json"
        if config_file.exists():
            return {
                "status": "pass",
                "summary": "SenseVoice 模型已就绪",
                "detail": str(model_root),
                "raw_output": f"[INFO] 已检测到 SenseVoice 模型目录: {model_root}",
            }

        buffer = io.StringIO()
        result_holder: Dict[str, Any] = {"ready": False, "error": ""}

        def worker() -> None:
            try:
                with redirect_stdout(buffer), redirect_stderr(buffer):
                    result_holder["ready"] = check_and_download_sensevoice()
            except Exception as exc:
                result_holder["error"] = str(exc)

        thread = threading.Thread(target=worker, daemon=True, name="SenseVoiceAssetCheck")
        thread.start()
        thread.join(45)

        output = buffer.getvalue().strip()
        if thread.is_alive():
            timeout_text = "[WARN] SenseVoice 模型自动补齐超时，已跳过本次下载。"
            output = f"{output}\n{timeout_text}".strip()
            return {
                "status": "warn",
                "summary": "SenseVoice 模型尚未就绪",
                "detail": str(model_root),
                "raw_output": output,
            }

        if result_holder["error"]:
            output = f"{output}\n[ERROR] {result_holder['error']}".strip()
            return {
                "status": "error",
                "summary": "SenseVoice 模型补齐失败",
                "detail": str(model_root),
                "raw_output": output,
            }

        if not output:
            output = "[INFO] 已完成 SenseVoice 模型资产检查。"
        return {
            "status": "pass" if result_holder["ready"] else "warn",
            "summary": "SenseVoice 模型已自动补齐" if result_holder["ready"] else "SenseVoice 模型尚未就绪",
            "detail": str(model_root),
            "raw_output": output,
        }

    def _check_rag_assets(self) -> Dict[str, Any]:
        scopes = knowledge_manager.list_scopes(include_known_experts=True)
        available = [row for row in scopes if row["doc_count"] or row["vector_ready"] or row["structured_ready"]]
        detail_parts = [f"{row['scope']} docs={row['doc_count']}" for row in available[:8]]
        return {
            "status": "pass" if scopes else "error",
            "summary": f"已发现 {len(scopes)} 个知识库作用域" if scopes else "未发现可用知识库目录",
            "detail": ", ".join(detail_parts) if detail_parts else str(resource_path("pc/knowledge_base")),
            "raw_output": "[INFO] 已成功扫描到本地实验室知识库目录及结构.",
        }

    def get_knowledge_base_catalog(self) -> List[Dict[str, Any]]:
        return knowledge_manager.list_scopes(include_known_experts=True)

    def get_expert_catalog(self) -> List[Dict[str, Any]]:
        return expert_manager.list_expert_catalog()

    def get_archive_catalog(self) -> List[Dict[str, Any]]:
        return self.experiment_archive.list_sessions(limit=80)

    def get_archive_detail(self, session_id: str) -> Dict[str, Any]:
        return self.experiment_archive.get_session_detail(session_id)

    def get_training_overview(self) -> Dict[str, Any]:
        return training_manager.overview()

    def build_training_workspace(self, workspace_name: str = "") -> Dict[str, Any]:
        summary = training_manager.build_training_workspace(
            workspace_name=workspace_name or str(get_config("training.workspace_name", "labdetector_training"))
        )
        self._log_info(f"训练工作区已生成: {summary['workspace_dir']}")
        return summary

    def import_llm_training_data(self, paths: List[str]) -> Dict[str, Any]:
        summary = training_manager.import_llm_dataset(paths)
        self._log_info(
            f"LLM 训练数据导入完成: 新增 {summary['sample_count']} 条，总计 {summary['total_sample_count']} 条"
        )
        return summary

    def import_pi_training_data(self, paths: List[str]) -> Dict[str, Any]:
        summary = training_manager.import_pi_dataset(paths)
        self._log_info(f"Pi 训练数据导入完成: 样本 {summary['sample_count']}，配置 {summary['dataset_yaml']}")
        return summary

    def start_llm_finetune(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        self._ensure_training_dependencies_ready()
        job = training_manager.start_llm_job(payload)
        self._log_info(f"LLM 微调任务已启动: {job['job_id']}")
        return job

    def start_pi_detector_finetune(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        self._ensure_training_dependencies_ready()
        job = training_manager.start_pi_job(payload)
        self._log_info(f"Pi 检测模型微调任务已启动: {job['job_id']}")
        return job

    def start_full_training_pipeline(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        self._ensure_training_dependencies_ready()
        job = training_manager.start_full_pipeline_job(payload)
        self._log_info(f"一键全流程训练任务已启动: {job['job_id']}")
        return job

    def activate_llm_deployment(self, target: str = "") -> Dict[str, Any]:
        summary = training_manager.activate_llm_deployment(target)
        self._log_info(f"LLM 部署已激活: {summary.get('name', '')}")
        return summary

    def activate_pi_deployment(self, target: str = "") -> Dict[str, Any]:
        summary = training_manager.activate_pi_deployment(target)
        self._log_info(f"Pi 检测模型已激活: {summary.get('name', '')}")
        return summary
    @staticmethod
    def _parse_session_tags(raw: Any) -> List[str]:
        if isinstance(raw, list):
            return [str(item).strip() for item in raw if str(item).strip()]
        text = str(raw or "").replace(";", ",")
        return [part.strip() for part in text.split(",") if part.strip()]

    def _open_archive_session(self) -> str:
        meta = dict(self.session_metadata)
        meta.update(
            {
                "mode": self.mode,
                "source": "pc_local" if self.mode == "camera" else "pi_cluster",
                "backend": self.ai_backend,
                "model": self.selected_model,
            }
        )
        self.archive_session_id = self.experiment_archive.open_session(meta)
        return self.archive_session_id

    def _close_archive_session(self) -> None:
        if self.archive_session_id:
            try:
                self.experiment_archive.close_session()
            finally:
                self.archive_session_id = ""

    def _record_archive_event(self, event_type: str, payload: Dict[str, Any], title: str = "", frame: Optional[np.ndarray] = None) -> None:
        if not self.archive_session_id:
            return
        enriched = dict(self.session_metadata)
        enriched.update(payload)
        enriched.setdefault("mode", self.mode)
        enriched.setdefault("backend", self.ai_backend)
        enriched.setdefault("model", self.selected_model)
        if frame is not None:
            try:
                archive_root = Path(resource_path("pc/log/experiment_archives")) / self.archive_session_id / "frames"
                archive_root.mkdir(parents=True, exist_ok=True)
                frame_path = archive_root / f"{int(time.time() * 1000)}_{event_type}.jpg"
                cv2.imwrite(str(frame_path), frame)
                enriched["frame_path"] = str(frame_path)
            except Exception:
                pass
        self.experiment_archive.record_event(event_type, enriched, title=title)

    def import_expert_assets(self, expert_code: str, paths: List[str]) -> Dict[str, Any]:
        summary = expert_manager.import_expert_assets(expert_code, paths)
        self._log_info(
            f"专家模型导入完成: {summary['display_name']}，成功 {summary['imported_count']} 项，失败 {summary['failed_count']} 项"
        )
        return summary

    def get_cloud_backend_catalog(self) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for backend in service_provider_keys():
            config = get_backend_runtime_config(backend)
            requires_api_key = bool(config.get("requires_api_key"))
            config["configured"] = bool(config.get("base_url")) and (bool(config.get("api_key")) or not requires_api_key)
            rows.append(config)
        return rows

    def save_cloud_backend_config(self, backend: str, api_key: str = "", base_url: str = "", model: str = "") -> Dict[str, Any]:
        summary = save_backend_runtime_config(backend, api_key=api_key, base_url=base_url, model=model)
        self._log_info(f"模型服务配置已保存: {summary['label']}")
        return summary

    def import_knowledge_paths(
        self,
        paths: List[str],
        scope_name: str = "common",
        reset_index: bool = False,
        structured: bool = True,
    ) -> Dict[str, Any]:
        summary = knowledge_manager.import_paths(
            paths,
            scope_name=scope_name,
            reset_index=reset_index,
            structured=structured,
        )
        extra = str(summary.get("vector_error") or "").strip()
        message = f"知识库导入完成: 作用域={summary['scope']}，成功 {summary['imported_count']} 项，失败 {summary['failed_count']} 项"
        if extra:
            message = f"{message}；向量状态: {extra}"
        self._log_info(message)
        return summary

    def start_session(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        with self.lock:
            if self.session_active:
                self._stop_session_locked(announce=False)
            self._reset_logs()
            self._refresh_shadow_demo_config()
            self.ai_backend = str(payload.get("ai_backend") or "ollama")
            custom_model = str(payload.get("custom_model") or "").strip()
            selected_model = str(payload.get("selected_model") or "").strip()
            self.selected_model = custom_model or selected_model or self._default_model_for(self.ai_backend)
            self.mode = str(payload.get("mode") or "camera")
            self.expected_nodes = max(1, int(payload.get("expected_nodes") or 1))
            self.session_metadata = {
                "project_name": str(payload.get("project_name") or get_config("session_defaults.project_name", "AI4S 实验项目")).strip(),
                "experiment_name": str(payload.get("experiment_name") or get_config("session_defaults.experiment_name", "桌面监控实验")).strip(),
                "operator_name": str(payload.get("operator_name") or get_config("session_defaults.operator_name", "")).strip(),
                "tags": self._parse_session_tags(payload.get("tags") or get_config("session_defaults.tags", "桌面端,监控,AI4S")),
            }
            set_config("session_defaults.project_name", self.session_metadata["project_name"])
            set_config("session_defaults.experiment_name", self.session_metadata["experiment_name"])
            set_config("session_defaults.operator_name", self.session_metadata["operator_name"])
            set_config("session_defaults.tags", ",".join(self.session_metadata["tags"]))
            self.session_active = True
            self.session_phase = "starting"
            self.status_message = "正在启动监控"
            self.started_at = time.time()
            self.stop_event = threading.Event()
            self.latest_inference_result = {"text": "", "timestamp": 0.0}
            self.last_inference_log_ts = 0.0
            self.local_frame = None
            self.topology = {}
            self.manager = None
            self.demo_sequence = []
            self.demo_index = 0
            self.demo_thread = None
            self._open_archive_session()
            try:
                self._configure_backend()

                if self.mode == "camera":
                    self._start_camera_session_locked()
                    self.status_message = "单机监控运行中"
                else:
                    self._start_websocket_session_locked()
                    self.status_message = f"集群监控运行中，目标节点 {self.expected_nodes}"

                if self.demo_mode_enabled:
                    self._start_shadow_demo_locked()
                    self.status_message = f"演示模式已启用，{self.status_message}"

                self._start_background_aux_services(start_local_microphone=self.mode == "camera")
                self.session_phase = "running"
                self._record_archive_event(
                    "session_start",
                    {"status_message": self.status_message, "expected_nodes": self.expected_nodes},
                    title="启动监控",
                )
                self._log_info(
                    f"监控会话已启动: backend={self.ai_backend}, model={self.selected_model}, mode={self.mode}"
                )
            except Exception:
                self._close_archive_session()
                self.session_metadata = {}
                raise
        return self.get_state()
    def stop_session(self) -> Dict[str, Any]:
        with self.lock:
            if not self.session_active and self.mode == "idle":
                return self.get_state()
            self._stop_session_locked(announce=True)
        return self.get_state()
    def _start_shadow_demo_locked(self) -> None:
        if not self.demo_mode_enabled:
            return
        from pc.core.expert_manager import expert_manager

        self.demo_sequence = expert_manager.build_demo_sequence()
        self.demo_index = 0
        if not self.demo_sequence:
            self._log_error("隐藏演示模式已开启，但未发现可轮播的专家模型")
            return
        self._log_info(
            f"隐藏演示模式已激活：共 {len(self.demo_sequence)} 个专家，轮播间隔 {int(self.demo_interval)} 秒"
        )
        self.demo_thread = threading.Thread(target=self._shadow_demo_loop, daemon=True, name="ShadowDemoLoop")
        self.demo_thread.start()

    def _shadow_demo_loop(self) -> None:
        while not self.stop_event.is_set():
            if not self.session_active or not self.demo_sequence:
                time.sleep(0.4)
                continue

            step = self.demo_sequence[self.demo_index % len(self.demo_sequence)]
            published = False
            if self.mode == "camera":
                if self.local_frame is not None:
                    self._publish_local_demo_step(step)
                    published = True
            elif self.mode == "websocket":
                if self.manager and self.topology:
                    online_nodes = [
                        node_id for node_id in self.topology
                        if self.manager.node_status.get(node_id, "offline") == "online"
                    ]
                    if online_nodes:
                        self._publish_websocket_demo_step(step, online_nodes)
                        published = True

            if not published:
                time.sleep(0.5)
                continue

            self.demo_index += 1
            wait_until = time.time() + self.demo_interval
            while not self.stop_event.is_set() and time.time() < wait_until:
                time.sleep(0.25)

    def _publish_local_demo_step(self, step: Dict[str, Any]) -> None:
        message = str(step.get("hint") or "")
        with self.lock:
            self.latest_inference_result = {
                "text": message,
                "timestamp": time.time(),
                "demo": True,
                "expert": step.get("expert_name", ""),
            }
            self.status_message = f"演示模式进行中：{step.get('expert_name', '')}"
        self._log_info(str(step.get("log") or message))

    def _publish_websocket_demo_step(self, step: Dict[str, Any], online_nodes: List[str]) -> None:
        if not self.manager:
            return
        now = time.time()
        message = str(step.get("hint") or "")
        for node_id in online_nodes:
            self.manager.node_latest_results[node_id] = {
                "text": message,
                "event_name": step.get("event_name", "演示事件"),
                "timestamp": now,
                "demo": True,
                "expert": step.get("expert_name", ""),
            }
        with self.lock:
            self.status_message = f"演示模式进行中：{step.get('expert_name', '')}"
        self._log_info(str(step.get("log") or message))

    def _configure_backend(self) -> None:
        set_config("ai_backend.type", self.ai_backend)
        if self.ai_backend != "ollama":
            try:
                save_backend_runtime_config(self.ai_backend, model=self.selected_model)
            except Exception:
                pass
        set_ai_backend(self.ai_backend, self.selected_model)
        if self.ai_backend == "ollama":
            self._ensure_ollama_service()

    def _ensure_ollama_service(self) -> None:
        ollama_exe = "ollama"
        default_path = Path(r"C:\Users\Administrator\AppData\Local\Programs\Ollama\ollama.exe")
        if os.name == "nt" and default_path.exists():
            ollama_exe = str(default_path)
        creation_flags = 0x08000000 if os.name == "nt" else 0
        try:
            popen_hidden(
                [ollama_exe, "serve"],
                creationflags=creation_flags,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            time.sleep(0.2)
        except Exception as exc:
            self._log_error(f"尝试拉起 Ollama 服务失败: {exc}")

    def _ensure_scheduler(self) -> None:
        if self.scheduler_started:
            return
        try:
            from pc.core.scheduler_manager import scheduler_manager
            scheduler_manager.start()
            self._scheduler_manager = scheduler_manager
            self.scheduler_started = True
        except Exception as exc:
            self._log_error(f"定时任务引擎启动失败: {exc}")

    def _ensure_voice_agent(self, start_local_microphone: bool) -> None:
        try:
            from pc.voice.voice_interaction import get_voice_interaction
            agent = get_voice_interaction()
            self.voice_agent = agent
            if not agent:
                return
            agent.set_ai_backend(self.ai_backend, self.selected_model)
            agent.get_latest_frame_callback = self._latest_frame_for_voice
            source = "pc_local" if start_local_microphone else "pi_cluster"
            agent.open_runtime_session(
                mode=self.mode or "idle",
                source=source,
                metadata={"expected_nodes": self.expected_nodes, "archive_session_id": self.archive_session_id, **self.session_metadata},
            )
            if start_local_microphone:
                if not agent.is_running:
                    if agent.start():
                        self._log_info("语音助手已启动")
                    else:
                        self._log_error("语音助手启动失败，可能未插入麦克风")
            elif agent.is_running:
                agent.stop()
                self._log_info("已切换到树莓派语音模式，PC 本地麦克风监听已关闭")
        except Exception as exc:
            self._log_error(f"语音助手初始化失败: {exc}")

    def _start_background_aux_services(self, *, start_local_microphone: bool) -> None:
        def worker() -> None:
            try:
                self._ensure_scheduler()
                self._ensure_voice_agent(start_local_microphone=start_local_microphone)
            except Exception as exc:
                self._log_error(f"后台附属模块初始化失败: {exc}")

        self.background_init_thread = threading.Thread(
            target=worker,
            daemon=True,
            name="RuntimeAuxInit",
        )
        self.background_init_thread.start()

    def _latest_frame_for_voice(self) -> Optional[np.ndarray]:
        if self.local_frame is not None:
            return self.local_frame
        if self.manager:
            for frame in self.manager.frame_buffers.values():
                if frame is not None:
                    return frame
        return None

    def _start_camera_session_locked(self) -> None:
        self.capture = cv2.VideoCapture(0)
        if not self.capture.isOpened():
            self.capture.release()
            self.capture = None
            self.session_active = False
            self.session_phase = "error"
            raise RuntimeError("无法打开本机摄像头")

        # Lower the local camera load first to keep preview and voice interaction responsive.
        try:
            self.capture.set(cv2.CAP_PROP_FRAME_WIDTH, 960)
            self.capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 540)
            self.capture.set(cv2.CAP_PROP_FPS, 15)
            if hasattr(cv2, "CAP_PROP_BUFFERSIZE"):
                self.capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception:
            pass

        self.camera_thread = threading.Thread(target=self._camera_capture_loop, daemon=True, name="CameraCapture")
        self.camera_thread.start()
        if self.demo_mode_enabled:
            self.inference_thread = None
            self._log_info("隐藏演示模式已接管本机专家提示轮播，真实本机推理已暂停")
        else:
            self.inference_thread = threading.Thread(target=self._camera_inference_loop, daemon=True, name="CameraInference")
            self.inference_thread.start()

    def _camera_capture_loop(self) -> None:
        read_failures = 0
        while not self.stop_event.is_set():
            capture = self.capture
            if capture is None:
                break
            ok, frame = capture.read()
            if self.stop_event.is_set():
                break
            if not ok:
                read_failures += 1
                if read_failures == 1 and not self.stop_event.is_set():
                    self._log_error("摄像头读取失败，正在重试")
                time.sleep(0.2)
                continue

            read_failures = 0
            with self.lock:
                self.local_frame = frame

            try:
                self.inference_queue.put_nowait(frame)
            except queue.Full:
                try:
                    self.inference_queue.get_nowait()
                except queue.Empty:
                    pass
                try:
                    self.inference_queue.put_nowait(frame)
                except queue.Full:
                    pass

        if self.capture is not None:
            self.capture.release()
            self.capture = None

    def _camera_inference_loop(self) -> None:
        from pc.core.expert_manager import expert_manager

        interval = float(get_config("inference.interval", 1.0))
        event_name = str(get_config("inference.local_event_name", "综合安全巡检")).strip() or "综合安全巡检"
        last_inference = 0.0
        while not self.stop_event.is_set():
            try:
                frame = self.inference_queue.get(timeout=0.2)
            except queue.Empty:
                continue
            if time.time() - last_inference < interval:
                continue
            try:
                inference_frame = frame
                height, width = frame.shape[:2]
                if width > 640:
                    scaled_height = max(1, int(height * (640.0 / width)))
                    inference_frame = cv2.resize(frame, (640, scaled_height), interpolation=cv2.INTER_AREA)
                resident_bundle = expert_manager.analyze_resident_frame(
                    inference_frame,
                    {"source": "pc_local_camera", "event_name": event_name, "mode": "camera"},
                    media_type="video",
                )
                result = str(resident_bundle.get("text") or "").strip()
                if result:
                    self.latest_inference_result = {"text": result, "timestamp": time.time()}
                    self._record_archive_event("local_inference", {"event_name": event_name, "result_text": result}, title="本机巡检", frame=inference_frame)
                    self._log_info(f"本机推理结果: {result}")
                    if not (self.voice_agent and getattr(self.voice_agent, "is_active", False)):
                        try:
                            from pc.core.tts import speak_async
                            speak_async(f"本地提示：{result}")
                        except Exception:
                            pass
                else:
                    now = time.time()
                    neutral_text = "本机巡检中，当前未发现需要提示的明显异常。"
                    self.latest_inference_result = {"text": neutral_text, "timestamp": now}
                    if now - self.last_inference_log_ts >= max(interval * 4, 6.0):
                        self._log_info(f"本机巡检已执行：事件={event_name}，当前未发现明确异常。")
                        self.last_inference_log_ts = now
                last_inference = time.time()
            except Exception as exc:
                self._log_error(f"本机推理线程异常: {exc}")
                time.sleep(0.5)

    def _start_websocket_session_locked(self) -> None:
        import pc.communication.network_scanner as network_scanner

        topology = network_scanner.scan_multi_nodes(self.expected_nodes)
        if not topology:
            self.session_active = False
            self.session_phase = "error"
            raise RuntimeError("未扫描到可用树莓派节点")

        self.topology = topology
        if len(topology) < self.expected_nodes:
            self._log_error(f"仅发现 {len(topology)} 个节点，低于预期 {self.expected_nodes} 个")
        else:
            self._log_info(f"已发现 {len(topology)} 个树莓派节点")

        self.manager = DashboardMultiPiManager(
            topology,
            self._log_info,
            self._log_error,
            selected_model=self.selected_model,
            archive_event=self._record_archive_event,
        )
        self.manager_thread = threading.Thread(target=self._manager_loop, daemon=True, name="MultiNodeManager")
        self.manager_thread.start()

    def _manager_loop(self) -> None:
        try:
            if self.manager:
                asyncio.run(self.manager.start())
        except Exception as exc:
            self._log_error(f"多节点监控线程退出: {exc}")

    def _stop_session_locked(self, announce: bool) -> None:
        had_running_session = bool(self.session_active or self.mode != "idle" or self.local_frame is not None or self.topology)
        if self.stop_event:
            self.stop_event.set()
        if self.manager:
            self.manager.stop()
            self.manager = None
        if self.capture is not None:
            self.capture.release()
            self.capture = None
        if self.voice_agent:
            try:
                if getattr(self.voice_agent, "is_running", False):
                    self.voice_agent.stop()
                close_session = getattr(self.voice_agent, "close_runtime_session", None)
                if callable(close_session):
                    close_session()
            except Exception:
                pass
        self._close_archive_session()

        self.local_frame = None
        self.latest_inference_result = {"text": "", "timestamp": 0.0}
        self.last_inference_log_ts = 0.0
        self.topology = {}
        self.demo_sequence = []
        self.demo_index = 0
        self.demo_thread = None
        self.session_active = False
        self.session_phase = "idle"
        self.mode = "idle"
        self.status_message = "待机"
        if announce and had_running_session:
            self._log_info("监控会话已停止")

    def _build_streams(self) -> List[Dict[str, Any]]:
        if self.mode == "camera":
            result_text = self.latest_inference_result.get("text", "")
            if result_text and not self.demo_mode_enabled and time.time() - float(self.latest_inference_result.get("timestamp", 0.0)) > 8:
                result_text = ""
            if self.session_active or self.local_frame is not None:
                return [{
                    "id": "local",
                    "title": "本机摄像头",
                    "subtitle": "统一专家矩阵 · 演示模式" if self.demo_mode_enabled else "统一专家矩阵",
                    "status": "online" if self.local_frame is not None else "connecting",
                    "hint": result_text or "等待最新画面与研判结果",
                    "address": "Local Device",
                    "caps": {"has_mic": True, "has_speaker": True},
                }]
            return []

        if self.mode == "websocket" and self.topology:
            streams = []
            for node_id, ip in sorted(self.topology.items(), key=lambda item: item[0]):
                status = "offline"
                caps = {"has_mic": False, "has_speaker": False}
                hint = "等待边缘事件回传"
                if self.manager:
                    status = self.manager.node_status.get(node_id, "offline")
                    caps = self.manager.node_caps.get(node_id, caps)
                    latest = self.manager.node_latest_results.get(node_id, {})
                    hint = latest.get("text") or self._status_hint(status)
                streams.append({
                    "id": node_id,
                    "title": f"节点 {node_id}",
                    "subtitle": "边缘视觉联动 · 演示模式" if self.demo_mode_enabled else "边缘视觉联动",
                    "status": status,
                    "hint": hint,
                    "address": ip,
                    "caps": caps,
                })
            return streams
        return []

    def _status_hint(self, status: str) -> str:
        hints = {
            "online": "已连接，等待边缘视觉事件",
            "connecting": "正在连接节点",
            "offline": "节点离线，后台自动重连中",
        }
        return hints.get(status, "等待状态更新")

    def frame_bytes(self, stream_id: str) -> bytes:
        frame = self._compose_frame(stream_id)
        ok, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 82])
        if not ok:
            raise RuntimeError("帧编码失败")
        return encoded.tobytes()

    def _compose_frame(self, stream_id: str) -> np.ndarray:
        title = "未知流"
        status = "offline"
        hint = "暂无画面"
        frame: Optional[np.ndarray] = None

        if stream_id == "local":
            title = "本机摄像头"
            status = "online" if self.local_frame is not None else "connecting"
            hint = self.latest_inference_result.get("text") or self._status_hint(status)
            frame = self.local_frame.copy() if self.local_frame is not None else None
        else:
            title = f"节点 {stream_id}"
            if self.manager:
                status = self.manager.node_status.get(stream_id, "offline")
                hint = self.manager.node_latest_results.get(stream_id, {}).get("text") or self._status_hint(status)
                source = self.manager.frame_buffers.get(stream_id)
                frame = source.copy() if source is not None else None

        if frame is None:
            frame = self._placeholder_frame(title, status, hint)
        else:
            frame = cv2.resize(frame, (960, 540))
            self._draw_frame_badges(frame, title, status, hint)
        return frame

    def _placeholder_frame(self, title: str, status: str, hint: str) -> np.ndarray:
        frame = np.zeros((540, 960, 3), dtype=np.uint8)
        for row in range(frame.shape[0]):
            intensity = 22 + int(34 * row / frame.shape[0])
            frame[row, :, :] = (intensity, intensity + 8, intensity + 18)
        self._draw_frame_badges(frame, title, status, hint)
        return frame

    def _draw_frame_badges(self, frame: np.ndarray, title: str, status: str, hint: str) -> None:
        overlay = frame.copy()
        cv2.rectangle(overlay, (0, 0), (960, 78), (10, 18, 27), -1)
        cv2.rectangle(overlay, (0, 462), (960, 540), (8, 14, 24), -1)
        cv2.addWeighted(overlay, 0.72, frame, 0.28, 0, frame)
        accent = {
            "online": (72, 220, 163),
            "connecting": (255, 194, 92),
            "offline": (255, 105, 105),
        }.get(status, (255, 194, 92))
        cv2.rectangle(frame, (24, 24), (36, 54), accent, -1)
        self._draw_text(frame, title, (56, 22), (245, 247, 250), 26)
        self._draw_text(frame, status.upper(), (56, 50), accent, 18)
        y = 478
        for line in self._wrap_text(hint, 34)[:2]:
            self._draw_text(frame, line, (24, y), (224, 230, 238), 22)
            y += 28

    def _draw_text(self, frame: np.ndarray, text: str, position: tuple[int, int], color: tuple[int, int, int], font_size: int) -> None:
        if not text:
            return
        if HAS_PIL:
            try:
                image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                draw = ImageDraw.Draw(image)
                font = None
                for font_name in FONT_CANDIDATES:
                    try:
                        font = ImageFont.truetype(font_name, font_size)
                        break
                    except Exception:
                        continue
                if font is None:
                    font = ImageFont.load_default()
                draw.text(position, text, font=font, fill=(color[2], color[1], color[0]))
                frame[:, :, :] = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
                return
            except Exception:
                pass
        cv2.putText(frame, text, position, cv2.FONT_HERSHEY_SIMPLEX, max(font_size / 32.0, 0.5), color, 2, cv2.LINE_AA)

    def _wrap_text(self, text: str, width: int) -> List[str]:
        if len(text) <= width:
            return [text]
        return [text[idx : idx + width] for idx in range(0, len(text), width)]

    def export_logs(self) -> Optional[str]:
        if not self.logs:
            return None
        log_dir = Path(resource_path("pc/log"))
        log_dir.mkdir(parents=True, exist_ok=True)
        path = log_dir / f"{time.strftime('%Y%m%d_%H%M%S')}_web_console.log"
        with path.open("w", encoding="utf-8-sig") as handle:
            for row in self.logs:
                rendered = row.get("rendered")
                if rendered is not None:
                    handle.write(f"{rendered}\n")
                else:
                    handle.write(f"[{row['timestamp']}] [{row['level']}] {row['text']}\n")
        return str(path)

    def shutdown(self) -> None:
        with self.lock:
            self._stop_session_locked(announce=False)
        if self._scheduler_manager and self.scheduler_started:
            try:
                self._scheduler_manager.stop()
            except Exception:
                pass
        exported = self.export_logs()
        if exported:
            self._log_info(f"可视化运行时日志已导出: {exported}")
