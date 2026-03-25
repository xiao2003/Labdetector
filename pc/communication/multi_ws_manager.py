import asyncio
import os
import time
from collections import deque
import websockets
import numpy as np
import cv2
import json
from pc.app_identity import resource_path
from pc.core.ai_backend import _STATE
from pc.core.logger import console_info, console_error
from pc.core.config import get_config
from pc.core.expert_manager import expert_manager
from pc.core.expert_closed_loop import (
    parse_pi_expert_packet,
    build_expert_result_command,
    parse_pi_expert_ack,
    ExpertResult,
)


class MultiPiManager:
    def __init__(self, pi_dict: dict):
        self.pi_dict = pi_dict
        self.frame_buffers = {pid: None for pid in pi_dict}
        self.send_queues = {pid: asyncio.Queue() for pid in pi_dict}
        self.running = True

        # Track per-node connectivity state for the dashboard and runtime.
        self.node_status = {pid: "connecting" for pid in pi_dict}
        self.node_caps = {pid: {"has_mic": False, "has_speaker": False} for pid in pi_dict}
        self.loop = None

        num_nodes = len(pi_dict)
        self.target_fps = max(1.0, 30.0 / num_nodes) if num_nodes > 0 else 30.0

        self.recent_event_ids = set()
        self.recent_event_queue = deque(maxlen=500)
        self.pending_result_acks = {}
        self.ack_timeout = float(get_config("expert_loop.ack_timeout", 2.0))
        self.ack_retries = int(get_config("expert_loop.ack_retries", 2))
        self.event_queue = asyncio.Queue(maxsize=int(get_config("expert_loop.max_pending_events", 32) or 32))
        self.event_worker_count = max(1, int(get_config("expert_loop.worker_count", 1) or 1))
        self.event_cooldown = float(get_config("expert_loop.event_cooldown_seconds", 6.0) or 6.0)
        self.recent_policy_hits = {}

        self.audit_log_dir = str(resource_path("pc/log"))
        os.makedirs(self.audit_log_dir, exist_ok=True
        )

    def _write_audit(self, text: str):
        path = os.path.join(self.audit_log_dir, "expert_closed_loop.log")
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {text}\n")

    async def _send_with_ack(self, ws, pi_id: str, result: ExpertResult):
        cmd = build_expert_result_command(result)
        for attempt in range(self.ack_retries + 1):
            await self.send_queues[pi_id].put(cmd)
            self.pending_result_acks[(pi_id, result.event_id)] = time.time()
            await asyncio.sleep(self.ack_timeout)
            if (pi_id, result.event_id) not in self.pending_result_acks:
                return True
        return False

    async def _dispatch_expert_result(self, pi_id: str, event_name: str, result: ExpertResult):
        if not self.running or self.node_status.get(pi_id) != "online":
            return
        acked = await self._send_with_ack(None, pi_id, result)
        self._write_audit(
            f"node={pi_id} event={event_name} event_id={result.event_id} acked={acked} text={result.text}"
        )
        if not acked:
            console_error(f"节点 [{pi_id}] 未确认专家结论 ACK: {result.event_id}")

    def _should_skip_event(self, pi_id: str, event) -> bool:
        expert_code = str(event.expert_code or "").strip() or "|".join(expert_manager.closed_loop_codes_for_event(event.event_name))
        key = (str(pi_id), expert_code or str(event.event_name or "").strip())
        now = time.time()
        last_ts = float(self.recent_policy_hits.get(key, 0.0) or 0.0)
        if now - last_ts < self.event_cooldown:
            return True
        self.recent_policy_hits[key] = now
        return False

    async def _enqueue_edge_event(self, pi_id: str, event) -> None:
        if self._should_skip_event(pi_id, event):
            console_info(f"节点 [{pi_id}] 相同策略事件处于冷却期，已跳过: {event.event_name}")
            return
        try:
            self.event_queue.put_nowait((pi_id, event))
        except asyncio.QueueFull:
            console_error(f"节点 [{pi_id}] 边缘事件队列已满，已丢弃事件: {event.event_name}")

    async def _event_worker(self):
        from pc.voice.voice_interaction import get_remote_text_router

        while self.running or not self.event_queue.empty():
            try:
                pi_id, event = await asyncio.wait_for(self.event_queue.get(), timeout=0.5)
            except asyncio.TimeoutError:
                continue
            try:
                if not self.running:
                    continue
                console_info(f"收到节点 [{pi_id}] 边缘高优告警: {event.event_name} ({event.event_id})")
                agent = get_remote_text_router()
                if agent and agent.is_active:
                    console_info("语音助手处于活跃状态，暂缓播报边缘告警。")
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
                    "model": _STATE.get("selected_model", ""),
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
                    result = ExpertResult(
                        event_id=event.event_id,
                        text=tts_text,
                        severity="warning",
                        speak=self.node_caps.get(pi_id, {}).get("has_speaker", False),
                    )
                    await self._dispatch_expert_result(pi_id, event.event_name, result)
            except Exception as exc:
                console_error(f"节点 [{pi_id}] 边缘事件处理失败: {exc}")
            finally:
                self.event_queue.task_done()

    async def _node_handler(self, pi_id, ip):
        endpoint = str(ip).strip()
        if endpoint.startswith("ws://") or endpoint.startswith("wss://"):
            uri = endpoint
        elif ":" in endpoint:
            uri = f"ws://{endpoint}"
        else:
            uri = f"ws://{endpoint}:8001"
        # 将节点连接置于死循环中，断线后继续自动重连。
        while self.running:
            try:
                self.node_status[pi_id] = "connecting"
                async with websockets.connect(uri, ping_interval=None, proxy=None) as ws:
                    self.node_status[pi_id] = "online"
                    console_info(f"节点 [{pi_id}] ({ip}) 握手成功")
                    await self.send_queues[pi_id].put(f"CMD:SET_FPS:{self.target_fps}")

                    sync_data = {"wake_word": get_config("voice_interaction.wake_word", "小爱同学")}
                    await self.send_queues[pi_id].put(f"CMD:SYNC_CONFIG:{json.dumps(sync_data)}")

                    policies = expert_manager.get_aggregated_edge_policy()
                    await self.send_queues[pi_id].put(f"CMD:SYNC_POLICY:{json.dumps(policies)}")
                    console_info(f"已向节点 [{pi_id}] 下发 {len(policies['event_policies'])} 条专家策略")

                    async def recv_stream_task():
                        async for data in ws:
                            if not self.running: break

                            if isinstance(data, str):
                                if data.startswith("PI_VOICE_COMMAND:"):
                                    self._handle_remote_voice(pi_id, data)
                                elif data.startswith("PI_CAPS:"):
                                    caps_raw = data.replace("PI_CAPS:", "", 1)
                                    try:
                                        self.node_caps[pi_id] = json.loads(caps_raw)
                                        console_info(f"节点 [{pi_id}] 能力上报: {self.node_caps[pi_id]}")
                                    except Exception:
                                        pass
                                elif data.startswith("PI_EXPERT_ACK:"):
                                    ack, ack_err = parse_pi_expert_ack(data)
                                    if ack_err or not ack:
                                        console_error(f"专家回传 ACK 解析失败: {ack_err}")
                                        continue
                                    ack_event_id = str(ack.get("event_id", ""))
                                    self.pending_result_acks.pop((pi_id, ack_event_id), None)
                                    self._write_audit(f"node={pi_id} event_id={ack_event_id} ack={ack}")

                                # 处理完整的边缘事件接收与解码逻辑。
                                elif data.startswith("PI_EXPERT_EVENT:") or data.startswith("PI_YOLO_EVENT:"):
                                    event, parse_error = parse_pi_expert_packet(data)
                                    if parse_error or event is None:
                                        console_error(f"处理边缘告警事件异常: {parse_error}")
                                        continue

                                    if event.event_id in self.recent_event_ids:
                                        console_info(f"节点 [{pi_id}] 重复事件已忽略: {event.event_id}")
                                        continue
                                    self.recent_event_ids.add(event.event_id)
                                    self.recent_event_queue.append(event.event_id)
                                    while len(self.recent_event_ids) > self.recent_event_queue.maxlen:
                                        expired = self.recent_event_queue.popleft()
                                        self.recent_event_ids.discard(expired)

                                    await self._enqueue_edge_event(pi_id, event)
                                continue

                            # 处理常规预览视频流的解码。
                            arr = np.frombuffer(data, np.uint8)
                            frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                            if frame is not None:
                                self.frame_buffers[pi_id] = frame

                    async def send_command_task():
                        while self.running:
                            msg = await self.send_queues[pi_id].get()
                            await ws.send(msg)

                    await asyncio.gather(recv_stream_task(), send_command_task())
            except Exception as e:
                if self.running:
                    # 断线后不退出程序，而是标记为离线并继续后台重连。
                    self.node_status[pi_id] = "offline"
                    console_error(f"节点 [{pi_id}] ({ip}) 通信断开，正在后台尝试重连...")
                    await asyncio.sleep(5)

    def _handle_remote_voice(self, pi_id, data):
        cmd_text = data.replace("PI_VOICE_COMMAND:", "")
        console_info(f"收到节点 {pi_id} 语音指令: {cmd_text}")
        from pc.voice.voice_interaction import get_remote_text_router
        agent = get_remote_text_router()
        if not agent:
            self.send_to_node(pi_id, "CMD:TTS:PC 端语音助手未就绪，请检查依赖环境。")
            return

        def _reply(answer: str):
            message = str(answer or "").strip()
            if not message:
                return
            preview = message if len(message) <= 120 else f"{message[:117]}..."
            console_info(f"已回传节点 {pi_id} 语音播报: {preview}")
            self._write_audit(f"node={pi_id} voice_command={cmd_text} reply={message}")
            self.send_to_node(pi_id, f"CMD:TTS:{message}")

        import threading
        threading.Thread(target=agent.process_remote_command, args=(pi_id, cmd_text, _reply), daemon=True).start()

    async def start(self):
        self.loop = asyncio.get_running_loop()
        tasks = [self._node_handler(pid, ip) for pid, ip in self.pi_dict.items()]
        tasks.extend(self._event_worker() for _ in range(self.event_worker_count))
        await asyncio.gather(*tasks)

    def send_to_node(self, pi_id, text):
        queue_ref = self.send_queues.get(pi_id)
        if queue_ref is None:
            return
        if self.loop is not None and self.loop.is_running():
            self.loop.call_soon_threadsafe(queue_ref.put_nowait, text)
        else:
            queue_ref.put_nowait(text)

    def stop(self):
        self.running = False
        self.pending_result_acks.clear()
        self.recent_policy_hits.clear()
        while not self.event_queue.empty():
            try:
                self.event_queue.get_nowait()
                self.event_queue.task_done()
            except Exception:
                break

