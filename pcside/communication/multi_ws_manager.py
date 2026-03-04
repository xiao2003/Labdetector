import asyncio
import os
import time
from collections import deque
import websockets
import numpy as np
import cv2
import json
from pcside.core.logger import console_info, console_error
from pcside.core.config import get_config
from pcside.core.expert_manager import expert_manager
from pcside.core.tts import speak_async
from pcside.core.expert_closed_loop import (
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

        # ★ 新增：独立跟踪每个节点的状态
        self.node_status = {pid: "connecting" for pid in pi_dict}
        self.node_caps = {pid: {"has_mic": False, "has_speaker": False} for pid in pi_dict}

        num_nodes = len(pi_dict)
        self.target_fps = max(1.0, 30.0 / num_nodes) if num_nodes > 0 else 30.0

        self.recent_event_ids = set()
        self.recent_event_queue = deque(maxlen=500)
        self.pending_result_acks = {}
        self.ack_timeout = float(get_config("expert_loop.ack_timeout", 2.0))
        self.ack_retries = int(get_config("expert_loop.ack_retries", 2))

        self.audit_log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "log")
        os.makedirs(self.audit_log_dir, exist_ok=True
        )

    def _write_audit(self, text: str):
        path = os.path.join(self.audit_log_dir, "expert_closed_loop.log")
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {text}\n")

    async def _send_with_ack(self, ws, pi_id: str, result: ExpertResult):
        cmd = build_expert_result_command(result)
        for attempt in range(self.ack_retries + 1):
            await ws.send(cmd)
            self.pending_result_acks[(pi_id, result.event_id)] = time.time()
            await asyncio.sleep(self.ack_timeout)
            if (pi_id, result.event_id) not in self.pending_result_acks:
                return True
        return False

    async def _node_handler(self, pi_id, ip):
        uri = f"ws://{ip}:8001"
        # ★ 修复：将节点连接放入死循环中，实现断线后无限重连
        while self.running:
            try:
                self.node_status[pi_id] = "connecting"
                async with websockets.connect(uri, ping_interval=None) as ws:
                    self.node_status[pi_id] = "online"
                    console_info(f"节点 [{pi_id}] ({ip}) 握手成功")
                    await ws.send(f"CMD:SET_FPS:{self.target_fps}")

                    sync_data = {"wake_word": get_config("voice_interaction.wake_word", "小爱同学")}
                    await ws.send(f"CMD:SYNC_CONFIG:{json.dumps(sync_data)}")

                    policies = expert_manager.get_aggregated_edge_policy()
                    await ws.send(f"CMD:SYNC_POLICY:{json.dumps(policies)}")
                    console_info(f"已下发 {len(policies['event_policies'])} 条专家策略至节点 [{pi_id}]")

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

                                # 修复：恢复完整的数据接收与解码逻辑
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

                                    console_info(f"收到节点 [{pi_id}] 边缘端高优告警: {event.event_name} ({event.event_id})")

                                    from pcside.voice.voice_interaction import get_voice_interaction
                                    agent = get_voice_interaction()
                                    if agent and agent.is_active:
                                        console_info("语音助手正活跃，安防播报暂缓。")
                                        continue

                                    # 将 event_str 组装成上下文，确保通用安防专家能提取到具体的违规内容
                                    context = {"event_desc": event.event_name, "detected_classes": event.detected_classes, "metrics": event.capture_metrics}

                                    # 抛给专家矩阵进行分析和 RAG 日志归档
                                    tts_text = await asyncio.to_thread(
                                        expert_manager.route_and_analyze,
                                        event.event_name,
                                        event.frame,
                                        context
                                    )

                                    # 研判结论始终回传 Pi 端；有扬声器则同时触发语音播报
                                    if tts_text:
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
                                            console_error(f"节点 [{pi_id}] 对专家结论未确认 ACK: {event.event_id}")
                                        speak_async(f"节点 {pi_id} 安防警告：{tts_text}")
                                continue

                            # 处理常规预览视频流的渲染
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
                    # ★ 修复：断线后不再退出程序，而是标记为离线，等待5秒后进入下一次循环尝试重连
                    self.node_status[pi_id] = "offline"
                    console_error(f"节点 [{pi_id}] ({ip}) 通信断开，其他节点不受影响。正在后台尝试重连...")
                    await asyncio.sleep(5)

    def _handle_remote_voice(self, pi_id, data):
        cmd_text = data.replace("PI_VOICE_COMMAND:", "")
        console_info(f"收到节点 {pi_id} 语音指令: {cmd_text}")
        from pcside.voice.voice_interaction import get_voice_interaction
        agent = get_voice_interaction()
        if agent:
            import threading
            threading.Thread(target=agent._route_command, args=(cmd_text,), daemon=True).start()

    async def start(self):
        tasks = [self._node_handler(pid, ip) for pid, ip in self.pi_dict.items()]
        await asyncio.gather(*tasks)

    def send_to_node(self, pi_id, text):
        if pi_id in self.send_queues:
            self.send_queues[pi_id].put_nowait(text)

    def stop(self):
        self.running = False