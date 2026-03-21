#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Local virtual Pi node for PC/Pi closed-loop testing."""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Optional

import cv2
import numpy as np
import websockets

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from pi.testing.closed_loop_bridge import PiClosedLoopBridge, default_simulated_scenarios
except Exception:
    PiClosedLoopBridge = None
    default_simulated_scenarios = None


class VirtualPiNode:
    def __init__(
        self,
        *,
        node_id: str,
        camera_index: int,
        event_name: str,
        event_interval: float,
        voice_commands: list[str],
        voice_commands_file: str,
        voice_start_delay: float,
        voice_interval: float,
        log_path: str = "",
    ) -> None:
        self.node_id = node_id
        self.camera_index = camera_index
        self.event_name = event_name
        self.event_interval = max(0.0, event_interval)
        self.voice_commands = [item.strip() for item in voice_commands if str(item).strip()]
        if voice_commands_file:
            try:
                extra_text = Path(voice_commands_file).read_text(encoding="utf-8-sig")
                self.voice_commands.extend([item.strip() for item in extra_text.splitlines() if item.strip()])
            except Exception as exc:
                self._log("voice_commands_file_error", error=str(exc), path=voice_commands_file)
        self.voice_start_delay = max(0.0, voice_start_delay)
        self.voice_interval = max(0.5, voice_interval)
        self.log_path = str(log_path or "").strip()
        self.sleep_time = 0.2
        self.policies: list[dict[str, Any]] = []
        self.last_event_ts = 0.0
        self.capture: Optional[cv2.VideoCapture] = None
        self.connected_at = 0.0
        self.last_voice_ts = 0.0
        self.last_preview_ts = 0.0
        self._send_lock: Optional[asyncio.Lock] = None
        self.bridge = PiClosedLoopBridge() if PiClosedLoopBridge is not None else None
        self.synthetic_scenarios = default_simulated_scenarios(self.node_id) if default_simulated_scenarios is not None else []
        self._log("bridge_init", enabled=bool(self.bridge), scenario_count=len(self.synthetic_scenarios))

    def _log(self, kind: str, **payload: Any) -> None:
        record = {"ts": time.time(), "kind": kind, "node_id": self.node_id, **payload}
        print(f"[virtual-pi:{self.node_id}] {kind} {payload}")
        if self.log_path:
            path = Path(self.log_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    def open_camera(self) -> None:
        if self.camera_index < 0:
            self.capture = None
            self._log("camera_synthetic", camera_index=self.camera_index)
            return
        self.capture = cv2.VideoCapture(self.camera_index)
        if not self.capture.isOpened():
            self.capture = None
            self._log("camera_fallback_synthetic", camera_index=self.camera_index)
            return
        self.capture.set(cv2.CAP_PROP_FRAME_WIDTH, 960)
        self.capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 540)
        self.capture.set(cv2.CAP_PROP_FPS, 15)
        self._log("camera_opened", camera_index=self.camera_index)

    def _synthetic_frame(self) -> np.ndarray:
        if self.synthetic_scenarios:
            return self.synthetic_scenarios[0].frame.copy()
        frame = np.full((540, 960, 3), 245, dtype=np.uint8)
        cv2.rectangle(frame, (40, 40), (920, 500), (30, 60, 90), 3)
        cv2.putText(frame, f"Virtual Pi {self.node_id}", (90, 120), cv2.FONT_HERSHEY_SIMPLEX, 1.6, (20, 20, 20), 4, cv2.LINE_AA)
        cv2.putText(frame, self.event_name, (90, 210), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (0, 90, 180), 3, cv2.LINE_AA)
        cv2.putText(frame, "HF", (380, 360), cv2.FONT_HERSHEY_SIMPLEX, 4.5, (0, 0, 0), 12, cv2.LINE_AA)
        cv2.putText(frame, "Wear gloves", (280, 450), cv2.FONT_HERSHEY_SIMPLEX, 1.4, (10, 10, 10), 3, cv2.LINE_AA)
        return frame

    def _weak_preview_frame(self) -> np.ndarray:
        frame = np.full((360, 640, 3), 26, dtype=np.uint8)
        cv2.rectangle(frame, (20, 20), (620, 340), (55, 75, 105), 2)
        cv2.putText(frame, f"Virtual Pi {self.node_id}", (42, 92), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (180, 220, 255), 2, cv2.LINE_AA)
        cv2.putText(frame, "idle preview", (42, 150), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (110, 150, 190), 2, cv2.LINE_AA)
        cv2.putText(frame, "key crops will be uploaded on demand", (42, 205), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (110, 150, 190), 2, cv2.LINE_AA)
        return frame

    def read_frame(self) -> np.ndarray:
        if self.capture is None:
            return self._synthetic_frame()
        ok, frame = self.capture.read()
        if not ok or frame is None:
            return self._synthetic_frame()
        return frame

    async def _send_packet(self, websocket: Any, payload: Any) -> None:
        if self._send_lock is None:
            self._send_lock = asyncio.Lock()
        async with self._send_lock:
            await websocket.send(payload)

    async def handle_client(self, websocket: Any) -> None:
        self.connected_at = time.time()
        connection_started_at = self.connected_at
        connection_voice_sent = 0
        self._send_lock = asyncio.Lock()
        self._log("client_connected", remote=str(websocket.remote_address))
        await self._send_packet(
            websocket,
            f"PI_CAPS:{json.dumps({'has_mic': True, 'has_speaker': True}, ensure_ascii=False)}",
        )

        async def recv_loop() -> None:
            async for message in websocket:
                if not isinstance(message, str):
                    continue
                if message.startswith("CMD:SET_FPS:"):
                    try:
                        target_fps = float(message.split(":")[-1])
                        self.sleep_time = 1.0 / max(1.0, target_fps)
                        self._log("set_fps", target_fps=target_fps)
                    except Exception:
                        pass
                elif message.startswith("CMD:SYNC_POLICY:"):
                    try:
                        payload = json.loads(message.replace("CMD:SYNC_POLICY:", "", 1))
                        self.policies = payload.get("event_policies", [])
                        summary = [
                            {
                                "event_name": str(item.get("event_name", "") or ""),
                                "expert_code": str(item.get("expert_code", "") or ""),
                                "trigger_classes": list(item.get("trigger_classes", []) or []),
                                "action": str(item.get("action", "") or ""),
                            }
                            for item in self.policies
                            if isinstance(item, dict)
                        ]
                        self._log("sync_policy", count=len(self.policies), summary=summary)
                    except Exception as exc:
                        self._log("sync_policy_error", error=str(exc))
                elif message.startswith("CMD:SYNC_CONFIG:"):
                    try:
                        payload = json.loads(message.replace("CMD:SYNC_CONFIG:", "", 1))
                        self._log("sync_config", payload=payload)
                    except Exception as exc:
                        self._log("sync_config_error", error=str(exc))
                elif message.startswith("CMD:EXPERT_RESULT:"):
                    try:
                        payload = json.loads(message.replace("CMD:EXPERT_RESULT:", "", 1))
                        event_id = str(payload.get("event_id") or "")
                        text = str(payload.get("text") or "").strip()
                        self._log("expert_result", event_id=event_id, text=text)
                        ack = {
                            "event_id": event_id,
                            "received": True,
                            "spoken": False,
                            "timestamp": time.time(),
                        }
                        await self._send_packet(websocket, f"PI_EXPERT_ACK:{json.dumps(ack, ensure_ascii=False)}")
                        self._log("expert_ack_sent", event_id=event_id)
                    except Exception as exc:
                        self._log("expert_result_error", error=str(exc))
                elif message.startswith("CMD:TTS:"):
                    text = message.replace("CMD:TTS:", "", 1)
                    self._log("tts_received", text=text)

        async def send_loop() -> None:
            nonlocal connection_voice_sent
            scenario_index = 0
            while True:
                await asyncio.sleep(max(0.03, self.sleep_time))
                frame = self.read_frame()
                now = time.time()
                preview_interval = 1.5 if self.camera_index < 0 else max(0.03, self.sleep_time)
                if (now - self.last_preview_ts) >= preview_interval:
                    preview = self._weak_preview_frame() if self.camera_index < 0 else cv2.resize(frame, (640, 360))
                    quality = 32 if self.camera_index < 0 else 75
                    ok, buf = cv2.imencode(".jpg", preview, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
                    if ok:
                        await self._send_packet(websocket, buf.tobytes())
                        self.last_preview_ts = now

                if self.event_interval > 0 and (time.time() - self.last_event_ts) >= self.event_interval:
                    sent_any = False
                    if self.bridge is not None and self.synthetic_scenarios and self.policies:
                        scenario = self.synthetic_scenarios[scenario_index % len(self.synthetic_scenarios)]
                        scenario_index += 1
                        triggered = self.bridge.trigger_events(
                            scenario.frame,
                            self.policies,
                            scenario.detected_objects,
                            scenario.boxes_dict,
                        )
                        packets = self.bridge.build_event_packets(
                            triggered,
                            capture_metrics={
                                **scenario.capture_metrics,
                                "camera_index": self.camera_index,
                                "node_id": self.node_id,
                            },
                        )
                        for packet in packets:
                            await self._send_packet(websocket, packet)
                            sent_any = True
                            try:
                                meta_raw = packet.split(":", 1)[1].rsplit(":", 1)[0]
                                meta = json.loads(meta_raw)
                            except Exception:
                                meta = {}
                            self._log(
                                "event_sent",
                                event_name=str(meta.get("event_name") or scenario.event_name),
                                event_id=str(meta.get("event_id") or ""),
                                expert_code=str(meta.get("expert_code") or ""),
                                detected_classes=str(meta.get("detected_classes") or ""),
                                bridge="pi.testing.closed_loop_bridge",
                            )
                    if not sent_any and self.bridge is None:
                        event_frame = cv2.resize(frame, (960, 540))
                        ok_hd, hd_buf = cv2.imencode(".jpg", event_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 88])
                        if ok_hd:
                            payload = {
                                "event_id": str(uuid.uuid4()),
                                "event_name": self.event_name,
                                "detected_classes": "person, bottle, hf_label",
                                "timestamp": time.time(),
                                "capture_metrics": {"source": "virtual_pi", "camera_index": self.camera_index, "node_id": self.node_id},
                            }
                            b64_img = base64.b64encode(hd_buf.tobytes()).decode("utf-8")
                            await self._send_packet(
                                websocket,
                                f"PI_EXPERT_EVENT:{json.dumps(payload, ensure_ascii=False)}:{b64_img}",
                            )
                            self._log("event_sent", event_name=self.event_name, event_id=payload["event_id"], bridge="legacy")
                            sent_any = True
                    if sent_any:
                        self.last_event_ts = time.time()

                if connection_voice_sent < len(self.voice_commands):
                    now = time.time()
                    ready_at = connection_started_at + self.voice_start_delay + connection_voice_sent * self.voice_interval
                    if now >= ready_at and (now - self.last_voice_ts) >= 0.6:
                        command = self.voice_commands[connection_voice_sent]
                        await self._send_packet(websocket, f"PI_VOICE_COMMAND:{command}")
                        self._log("voice_command_sent", index=connection_voice_sent, command=command)
                        connection_voice_sent += 1
                        self.last_voice_ts = now

        await asyncio.gather(recv_loop(), send_loop())

    async def run(self, host: str, port: int) -> None:
        self.open_camera()
        async with websockets.serve(self.handle_client, host, port, ping_interval=20, ping_timeout=20, max_size=None):
            self._log("server_started", endpoint=f"ws://{host}:{port}", camera_index=self.camera_index, event=self.event_name)
            while True:
                await asyncio.sleep(1)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="本地虚拟 Pi 节点")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址")
    parser.add_argument("--port", type=int, default=8001, help="监听端口")
    parser.add_argument("--camera-index", type=int, default=-1, help="本地摄像头索引，-1 表示使用合成画面")
    parser.add_argument("--event-name", default="综合安全巡检", help="周期上报的测试事件名")
    parser.add_argument("--event-interval", type=float, default=6.0, help="事件上报间隔，0 表示只推送视频流")
    parser.add_argument("--voice-commands", default="", help="要按顺序发送的语音命令，使用 || 分隔")
    parser.add_argument("--voice-commands-file", default="", help="UTF-8 语音命令文件，每行一条命令")
    parser.add_argument("--voice-start-delay", type=float, default=2.0, help="连接后首次发送语音命令的延迟")
    parser.add_argument("--voice-interval", type=float, default=4.0, help="多条语音命令之间的间隔")
    parser.add_argument("--log-path", default="", help="JSONL 日志输出文件")
    parser.add_argument("--node-id", default="1", help="节点编号")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    voice_commands = [item for item in str(args.voice_commands or "").split("||") if item.strip()]
    node = VirtualPiNode(
        node_id=str(args.node_id),
        camera_index=args.camera_index,
        event_name=args.event_name,
        event_interval=args.event_interval,
        voice_commands=voice_commands,
        voice_commands_file=str(args.voice_commands_file or ""),
        voice_start_delay=args.voice_start_delay,
        voice_interval=args.voice_interval,
        log_path=args.log_path,
    )
    try:
        asyncio.run(node.run(args.host, args.port))
    except KeyboardInterrupt:
        print(f"[virtual-pi:{args.node_id}] 已退出")


if __name__ == "__main__":
    main()
