import asyncio
import websockets
import numpy as np
import cv2
import base64
import json
from pcside.core.logger import console_info, console_error
from pcside.core.config import get_config
from pcside.core.expert_manager import expert_manager
from pcside.core.tts import speak_async


class MultiPiManager:
    def __init__(self, pi_dict: dict):
        self.pi_dict = pi_dict
        self.frame_buffers = {pid: None for pid in pi_dict}
        self.send_queues = {pid: asyncio.Queue() for pid in pi_dict}
        self.running = True

        # ★ 新增：独立跟踪每个节点的状态
        self.node_status = {pid: "connecting" for pid in pi_dict}

        num_nodes = len(pi_dict)
        self.target_fps = max(1.0, 30.0 / num_nodes) if num_nodes > 0 else 30.0

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

                                # 修复：恢复完整的数据接收与解码逻辑
                                elif data.startswith("PI_EXPERT_EVENT:") or data.startswith("PI_YOLO_EVENT:"):
                                    try:
                                        # 解析数据包 格式为: 事件前缀:事件名称:Base64图片
                                        _, event_str, b64_img = data.split(":", 2)
                                        img_bytes = base64.b64decode(b64_img)
                                        arr = np.frombuffer(img_bytes, np.uint8)
                                        expert_frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)

                                        console_info(f"收到节点 [{pi_id}] 边缘端高优告警: {event_str}")

                                        from pcside.voice.voice_interaction import get_voice_interaction
                                        agent = get_voice_interaction()
                                        if agent and agent.is_active:
                                            console_info("语音助手正活跃，安防播报暂缓。")
                                            continue

                                        # 将 event_str 组装成上下文，确保通用安防专家能提取到具体的违规内容
                                        context = {"event_desc": event_str}

                                        # 抛给专家矩阵进行分析和 RAG 日志归档
                                        tts_text = await asyncio.to_thread(
                                            expert_manager.route_and_analyze,
                                            event_str,
                                            expert_frame,
                                            context
                                        )

                                        # 如果专家返回了阻断语音，立刻下发并在 PC 端同步播报
                                        if tts_text:
                                            await ws.send(f"CMD:TTS:{tts_text}")
                                            speak_async(f"节点 {pi_id} 安防警告：{tts_text}")

                                    except Exception as e:
                                        console_error(f"处理边缘告警事件异常: {e}")
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