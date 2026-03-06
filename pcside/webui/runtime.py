#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Web runtime for the LabDetector dashboard."""

from __future__ import annotations

import asyncio
import importlib.util
import io
import json
import os
import queue
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

from pcside.core import logger as core_logger
from pcside.core.ai_backend import list_ollama_models, set_ai_backend
from pcside.core.config import get_config, set_config
from pcside.core.expert_closed_loop import (
    ExpertResult,
    build_expert_result_command,
    parse_pi_expert_ack,
    parse_pi_expert_packet,
)
from pcside.tools.model_downloader import check_and_download_vosk
from pcside.tools.version_manager import get_app_version
from pcside.knowledge_base.rag_engine import knowledge_manager

FONT_CANDIDATES = ["msyh.ttc", "simhei.ttf", "simsun.ttc", "Arial.ttf"]
DEPENDENCY_MAP = {
    "numpy": "numpy",
    "cv2": "opencv-python",
    "PIL": "pillow",
    "requests": "requests",
    "websockets": "websockets",
    "speech_recognition": "SpeechRecognition",
    "pyaudio": "pyaudio",
    "vosk": "vosk",
    "pyttsx3": "pyttsx3",
    "langchain_community": "langchain-community",
    "langchain_huggingface": "langchain-huggingface",
    "sentence_transformers": "sentence-transformers",
    "faiss": "faiss-cpu",
}


def _now_text() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


class DashboardMultiPiManager:
    def __init__(
        self,
        pi_dict: Dict[str, str],
        log_info: Callable[[str], None],
        log_error: Callable[[str], None],
    ) -> None:
        from pcside.communication.multi_ws_manager import MultiPiManager as BaseMultiPiManager

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
        self.audit_log_dir = self._base.audit_log_dir
        self._write_audit = self._base._write_audit
        self.log_info = log_info
        self.log_error = log_error
        self.node_latest_results: Dict[str, Dict[str, Any]] = {
            pid: {"text": "", "event_name": "", "timestamp": 0.0}
            for pid in pi_dict
        }

    async def _send_with_ack(self, ws: Any, pi_id: str, result: ExpertResult) -> bool:
        cmd = build_expert_result_command(result)
        for _ in range(self.ack_retries + 1):
            await ws.send(cmd)
            self.pending_result_acks[(pi_id, result.event_id)] = time.time()
            await asyncio.sleep(self.ack_timeout)
            if (pi_id, result.event_id) not in self.pending_result_acks:
                return True
        return False

    async def _node_handler(self, pi_id: str, ip: str) -> None:
        from pcside.core.expert_manager import expert_manager
        from pcside.voice.voice_interaction import get_voice_interaction

        uri = f"ws://{ip}:8001"
        while self.running:
            try:
                self.node_status[pi_id] = "connecting"
                async with websockets.connect(uri, ping_interval=None) as ws:
                    self.node_status[pi_id] = "online"
                    self.log_info(f"节点 [{pi_id}] ({ip}) 握手成功")
                    await ws.send(f"CMD:SET_FPS:{self.target_fps}")

                    sync_data = {"wake_word": get_config("voice_interaction.wake_word", "小爱同学")}
                    await ws.send(f"CMD:SYNC_CONFIG:{json.dumps(sync_data, ensure_ascii=False)}")

                    policies = expert_manager.get_aggregated_edge_policy()
                    await ws.send(f"CMD:SYNC_POLICY:{json.dumps(policies, ensure_ascii=False)}")
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

                                    self.log_info(f"收到节点 [{pi_id}] 边缘高优告警: {event.event_name} ({event.event_id})")
                                    agent = get_voice_interaction()
                                    if agent and agent.is_active:
                                        self.log_info("语音助手正在活跃，安防播报暂缓")
                                        continue

                                    context = {
                                        "event_desc": event.event_name,
                                        "detected_classes": event.detected_classes,
                                        "metrics": event.capture_metrics,
                                    }
                                    tts_text = await asyncio.to_thread(
                                        expert_manager.route_and_analyze,
                                        event.event_name,
                                        event.frame,
                                        context,
                                    )
                                    if tts_text:
                                        self.node_latest_results[pi_id] = {
                                            "text": tts_text,
                                            "event_name": event.event_name,
                                            "timestamp": time.time(),
                                        }
                                        result = ExpertResult(
                                            event_id=event.event_id,
                                            text=tts_text,
                                            severity="warning",
                                            speak=self.node_caps.get(pi_id, {}).get("has_speaker", False),
                                        )
                                        acked = await self._send_with_ack(ws, pi_id, result)
                                        self._write_audit(
                                            f"node={pi_id} event={event.event_name} event_id={event.event_id} acked={acked} text={tts_text}"
                                        )
                                        if not acked:
                                            self.log_error(f"节点 [{pi_id}] 对专家结论未确认 ACK: {event.event_id}")
                                        try:
                                            from pcside.core.tts import speak_async
                                            speak_async(f"节点 {pi_id} 安防提示：{tts_text}")
                                        except Exception:
                                            pass
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
        from pcside.voice.voice_interaction import get_voice_interaction

        cmd_text = data.replace("PI_VOICE_COMMAND:", "")
        self.log_info(f"收到节点 {pi_id} 语音指令: {cmd_text}")
        agent = get_voice_interaction()
        if agent:
            threading.Thread(target=agent._route_command, args=(cmd_text,), daemon=True).start()

    async def start(self) -> None:
        self.running = True
        self._base.running = True
        tasks = [self._node_handler(pid, ip) for pid, ip in self.pi_dict.items()]
        await asyncio.gather(*tasks)

    def send_to_node(self, pi_id: str, text: str) -> None:
        if pi_id in self.send_queues:
            self.send_queues[pi_id].put_nowait(text)

    def stop(self) -> None:
        self.running = False
        self._base.running = False


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
        self.inference_queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=1)

        self.capture: Optional[cv2.VideoCapture] = None
        self.camera_thread: Optional[threading.Thread] = None
        self.inference_thread: Optional[threading.Thread] = None
        self.manager_thread: Optional[threading.Thread] = None
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

    def _default_model_for(self, backend: str) -> str:
        if backend == "qwen":
            return str(get_config("qwen.model", "qwen-vl-max"))
        models = self._ollama_models()
        return models[0] if models else "llava:7b-v1.5-q4_K_M"

    def _refresh_shadow_demo_config(self) -> None:
        self.demo_mode_enabled = bool(get_config("shadow_demo.enabled", False))
        try:
            interval = float(get_config("shadow_demo.interval_seconds", 8))
        except (TypeError, ValueError):
            interval = 8.0
        self.demo_interval = max(4.0, interval)

    def _ollama_models(self) -> List[str]:
        raw_defaults = get_config("ollama.default_models", "llava:7b-v1.5-q4_K_M")
        if isinstance(raw_defaults, list):
            defaults = [str(item).strip() for item in raw_defaults if str(item).strip()]
        else:
            defaults = [item.strip() for item in str(raw_defaults).split(",") if item.strip()]

        discovered: List[str] = []
        try:
            discovered = list_ollama_models() or []
        except Exception as exc:
            self._log_error(f"刷新 Ollama 模型失败: {exc}")

        models = sorted(set(defaults + discovered))
        return models or defaults

    def refresh_model_catalog(self) -> Dict[str, List[str]]:
        return {
            "ollama": self._ollama_models(),
            "qwen": [str(get_config("qwen.model", "qwen-vl-max"))],
        }

    def bootstrap(self, include_self_check: bool = True) -> Dict[str, Any]:
        if include_self_check and not self.self_check_has_run:
            self.run_self_check()
        catalog = self.refresh_model_catalog()
        return {
            "version": self.version,
            "server": self.server_meta,
            "controls": {
                "backends": [
                    {"value": "ollama", "label": "Ollama (本地私有化大模型)"},
                    {"value": "qwen", "label": "Qwen3.5-Plus (阿里云端模型)"},
                ],
                "modes": [
                    {"value": "camera", "label": "本机摄像头模式"},
                    {"value": "websocket", "label": "树莓派集群WebSocket模式"},
                ],
                "models": catalog,
                "defaults": {
                    "ai_backend": self.ai_backend,
                    "selected_model": self.selected_model,
                    "mode": "camera",
                    "expected_nodes": 1,
                },
            },
            "knowledge_bases": self.get_knowledge_base_catalog(),
            "state": self.get_state(),
        }

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
            },
            "summary": summary,
            "self_check": self.self_check_results,
            "streams": streams,
            "logs": list(self.logs),
        }

    def run_self_check(self) -> List[Dict[str, Any]]:
        checks = [
            ("dependencies", "Python 依赖环境", self._check_dependencies),
            ("gpu", "GPU 算力环境", self._check_gpu),
            ("microphone", "PC 麦克风与语音链路", self._check_microphone),
            ("vosk", "离线语音模型资产", self._check_vosk_assets),
            ("rag", "实验室知识库目录 (RAG)", self._check_rag_assets),
        ]
        results: List[Dict[str, Any]] = []
        self._log_raw_line("")
        self._log_raw_line("=" * 55)
        self._log_raw_line(f"[INFO] LabDetector V{self.version} (PC 智算中枢) - 系统启动自检")
        self._log_raw_line("=" * 55)

        for index, (key, title, runner) in enumerate(checks, start=1):
            self._log_raw_line("")
            self._log_raw_line(f"[INFO] [{index}/5] 检查 {title}...")
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

        self._log_raw_line("")
        self._log_raw_line("=" * 55)
        self._log_raw_line("[INFO] 系统自检全部通过，正在启动主控制流...")
        self._log_raw_line("=" * 55)
        self._log_raw_line("")
        self.self_check_results = results
        self.self_check_has_run = True
        return results

    def _check_dependencies(self) -> Dict[str, Any]:
        missing = []
        installed = []
        for module_name, package_name in DEPENDENCY_MAP.items():
            if importlib.util.find_spec(module_name) is None:
                missing.append(package_name)
            else:
                installed.append(package_name)
        if missing:
            raw_output = f"[WARN] Python 关键依赖存在缺失: {', '.join(missing)}"
            return {
                "status": "warn",
                "summary": f"已加载 {len(installed)}/{len(DEPENDENCY_MAP)} 项关键依赖",
                "detail": "缺失依赖: " + ", ".join(missing),
                "raw_output": raw_output,
            }
        return {
            "status": "pass",
            "summary": f"{len(installed)} 项关键依赖已就绪",
            "detail": "requirements 对应核心依赖可导入",
            "raw_output": f"[INFO] Python 关键依赖检查通过，共 {len(installed)} 项.",
        }

    def _decode_subprocess_output(self, payload: bytes) -> str:
        for encoding in ("utf-8", "gbk", "cp936"):
            try:
                return payload.decode(encoding)
            except Exception:
                continue
        return payload.decode("utf-8", errors="ignore")

    def _run_python_script(self, relative_path: str) -> str:
        path = Path(__file__).resolve().parents[2] / relative_path
        result = subprocess.run(
            [sys.executable, str(path)],
            capture_output=True,
            timeout=60,
            cwd=str(path.parent.parent.parent),
        )
        output = self._decode_subprocess_output(result.stdout or b"") + self._decode_subprocess_output(result.stderr or b"")
        return output.strip()

    def _check_gpu(self) -> Dict[str, Any]:
        output = self._run_python_script("pcside/tools/check_gpu.py")
        status = "pass" if "GPU 可用: True" in output else "warn"
        summary = "检测到可用 GPU" if status == "pass" else "未检测到 CUDA，可降级到 CPU"
        return {
            "status": status,
            "summary": summary,
            "detail": output or "未返回输出",
            "raw_output": output or "[WARN] GPU 检查脚本未返回输出",
        }

    def _check_microphone(self) -> Dict[str, Any]:
        output = self._run_python_script("pcside/tools/check_mic.py")
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
        model_root = Path(__file__).resolve().parents[1] / "voice" / "model"
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

    def _check_rag_assets(self) -> Dict[str, Any]:
        scopes = knowledge_manager.list_scopes(include_known_experts=True)
        available = [row for row in scopes if row["doc_count"] or row["vector_ready"] or row["structured_ready"]]
        detail_parts = [f"{row['scope']} docs={row['doc_count']}" for row in available[:8]]
        return {
            "status": "pass" if scopes else "error",
            "summary": f"已发现 {len(scopes)} 个知识库作用域" if scopes else "未发现可用知识库目录",
            "detail": ", ".join(detail_parts) if detail_parts else str(Path(__file__).resolve().parents[1] / "knowledge_base"),
            "raw_output": "[INFO] 已成功扫描到本地实验室知识库目录及结构.",
        }

    def get_knowledge_base_catalog(self) -> List[Dict[str, Any]]:
        return knowledge_manager.list_scopes(include_known_experts=True)

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
            self._stop_session_locked(announce=False)
            self._refresh_shadow_demo_config()
            self.ai_backend = str(payload.get("ai_backend") or "ollama")
            custom_model = str(payload.get("custom_model") or "").strip()
            selected_model = str(payload.get("selected_model") or "").strip()
            self.selected_model = custom_model or selected_model or self._default_model_for(self.ai_backend)
            self.mode = str(payload.get("mode") or "camera")
            self.expected_nodes = max(1, int(payload.get("expected_nodes") or 1))
            self.session_active = True
            self.session_phase = "starting"
            self.status_message = "正在初始化监控会话"
            self.started_at = time.time()
            self.stop_event = threading.Event()
            self.latest_inference_result = {"text": "", "timestamp": 0.0}
            self.local_frame = None
            self.topology = {}
            self.manager = None
            self.demo_sequence = []
            self.demo_index = 0
            self.demo_thread = None

            self._configure_backend()
            self._ensure_scheduler()
            self._ensure_voice_agent()

            if self.mode == "camera":
                self._start_camera_session_locked()
                self.status_message = "本机摄像头监控已启动"
            else:
                self._start_websocket_session_locked()
                self.status_message = f"多节点监控已启动，目标节点数 {self.expected_nodes}"

            if self.demo_mode_enabled:
                self._start_shadow_demo_locked()
                self.status_message = f"隐藏演示模式已激活：{self.status_message}"

            self.session_phase = "running"
            self._log_info(
                f"监控会话已启动: backend={self.ai_backend}, model={self.selected_model}, mode={self.mode}"
            )
        return self.get_state()

    def stop_session(self) -> Dict[str, Any]:
        with self.lock:
            self._stop_session_locked(announce=True)
        return self.get_state()

    def _start_shadow_demo_locked(self) -> None:
        if not self.demo_mode_enabled:
            return
        from pcside.core.expert_manager import expert_manager

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
        if self.ai_backend == "qwen":
            set_config("qwen.model", self.selected_model)
        set_ai_backend(self.ai_backend)
        if self.ai_backend == "ollama":
            self._ensure_ollama_service()

    def _ensure_ollama_service(self) -> None:
        ollama_exe = "ollama"
        default_path = Path(r"C:\Users\Administrator\AppData\Local\Programs\Ollama\ollama.exe")
        if os.name == "nt" and default_path.exists():
            ollama_exe = str(default_path)
        creation_flags = 0x08000000 if os.name == "nt" else 0
        try:
            subprocess.Popen(
                [ollama_exe, "serve"],
                creationflags=creation_flags,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            time.sleep(1)
        except Exception as exc:
            self._log_error(f"尝试拉起 Ollama 服务失败: {exc}")

    def _ensure_scheduler(self) -> None:
        if self.scheduler_started:
            return
        try:
            from pcside.core.scheduler_manager import scheduler_manager
            scheduler_manager.start()
            self._scheduler_manager = scheduler_manager
            self.scheduler_started = True
        except Exception as exc:
            self._log_error(f"定时任务引擎启动失败: {exc}")

    def _ensure_voice_agent(self) -> None:
        try:
            from pcside.voice.voice_interaction import get_voice_interaction
            agent = get_voice_interaction()
            self.voice_agent = agent
            if not agent:
                return
            agent.set_ai_backend(self.ai_backend, self.selected_model)
            agent.get_latest_frame_callback = self._latest_frame_for_voice
            if not agent.is_running:
                if agent.start():
                    self._log_info("语音助手已启动")
                else:
                    self._log_error("语音助手启动失败，可能未插入麦克风")
        except Exception as exc:
            self._log_error(f"语音助手初始化失败: {exc}")

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
            if self.capture is None:
                break
            ok, frame = self.capture.read()
            if not ok:
                read_failures += 1
                if read_failures == 1:
                    self._log_error("摄像头读取失败，正在重试")
                time.sleep(0.2)
                continue

            read_failures = 0
            with self.lock:
                self.local_frame = frame.copy()

            try:
                self.inference_queue.put_nowait(frame.copy())
            except queue.Full:
                try:
                    self.inference_queue.get_nowait()
                except queue.Empty:
                    pass
                try:
                    self.inference_queue.put_nowait(frame.copy())
                except queue.Full:
                    pass

        if self.capture is not None:
            self.capture.release()
            self.capture = None

    def _camera_inference_loop(self) -> None:
        from pcside.core.expert_manager import expert_manager

        interval = float(get_config("inference.interval", 5))
        last_inference = 0.0
        while not self.stop_event.is_set():
            try:
                frame = self.inference_queue.get(timeout=0.2)
            except queue.Empty:
                continue
            if time.time() - last_inference < interval:
                continue
            try:
                result = expert_manager.route_and_analyze("Motion_Alert", frame, {})
                if result:
                    self.latest_inference_result = {"text": result, "timestamp": time.time()}
                    self._log_info(f"本机专家研判: {result}")
                    if not (self.voice_agent and getattr(self.voice_agent, "is_active", False)):
                        try:
                            from pcside.core.tts import speak_async
                            speak_async(f"本地提示：{result}")
                        except Exception:
                            pass
                last_inference = time.time()
            except Exception as exc:
                self._log_error(f"本机推理线程异常: {exc}")
                time.sleep(0.5)

    def _start_websocket_session_locked(self) -> None:
        import pcside.communication.network_scanner as network_scanner

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

        self.manager = DashboardMultiPiManager(topology, self._log_info, self._log_error)
        self.manager_thread = threading.Thread(target=self._manager_loop, daemon=True, name="MultiNodeManager")
        self.manager_thread.start()

    def _manager_loop(self) -> None:
        try:
            if self.manager:
                asyncio.run(self.manager.start())
        except Exception as exc:
            self._log_error(f"多节点监控线程退出: {exc}")

    def _stop_session_locked(self, announce: bool) -> None:
        if self.stop_event:
            self.stop_event.set()
        if self.manager:
            self.manager.stop()
            self.manager = None
        if self.capture is not None:
            self.capture.release()
            self.capture = None
        if self.voice_agent and getattr(self.voice_agent, "is_running", False):
            try:
                self.voice_agent.stop()
            except Exception:
                pass

        self.local_frame = None
        self.latest_inference_result = {"text": "", "timestamp": 0.0}
        self.topology = {}
        self.demo_sequence = []
        self.demo_index = 0
        self.demo_thread = None
        self.session_active = False
        self.session_phase = "idle"
        self.mode = "idle"
        self.status_message = "监控会话已停止"
        if announce:
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
        log_dir = Path(__file__).resolve().parents[1] / "log"
        log_dir.mkdir(parents=True, exist_ok=True)
        path = log_dir / f"{time.strftime('%Y%m%d_%H%M%S')}_web_console.log"
        with path.open("w", encoding="utf-8") as handle:
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

