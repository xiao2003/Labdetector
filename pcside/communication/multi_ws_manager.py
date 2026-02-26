# pcside/communication/multi_ws_manager.py
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

        # ==========================================
        # ★ 动态带宽均衡策略
        # ==========================================
        num_nodes = len(pi_dict)
        self.target_fps = max(1.0, 30.0 / num_nodes) if num_nodes > 0 else 30.0

    async def _node_handler(self, pi_id, ip):
        uri = f"ws://{ip}:8001"
        while self.running:
            try:
                async with websockets.connect(uri, ping_interval=None) as ws:
                    console_info(f"🔗 节点 [{pi_id}] ({ip}) 握手成功")
                    await ws.send(f"CMD:SET_FPS:{self.target_fps}")

                    # 1. 同步配置
                    sync_data = {"wake_word": get_config("voice_interaction.wake_word", "小爱同学")}
                    await ws.send(f"CMD:SYNC_CONFIG:{json.dumps(sync_data)}")

                    # 2. 下发专家策略
                    policies = expert_manager.get_aggregated_edge_policy()
                    await ws.send(f"CMD:SYNC_POLICY:{json.dumps(policies)}")
                    console_info(f"🧩 已下发 {len(policies['event_policies'])} 条专家策略至节点 [{pi_id}]")

                    async def recv_stream_task():
                        async for data in ws:
                            if not self.running: break

                            if isinstance(data, str):
                                if data.startswith("PI_VOICE_COMMAND:"):
                                    self._handle_remote_voice(pi_id, data)
                                # ★ 接收树莓派触发的高清关键帧 ★
                                elif data.startswith("PI_EXPERT_EVENT:"):
                                    try:
                                        _, event_name, b64_img = data.split(":", 2)
                                        img_bytes = base64.b64decode(b64_img)
                                        arr = np.frombuffer(img_bytes, np.uint8)
                                        expert_frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)

                                        console_info(f"⚡ 收到节点 [{pi_id}] 触发事件: {event_name}")
                                        # 路由给专家，获取播报文本
                                        tts_text = await asyncio.to_thread(expert_manager.route_and_analyze, event_name, expert_frame, {})

                                        if tts_text:
                                            await ws.send(f"CMD:TTS:{tts_text}")
                                            speak_async(f"节点 {pi_id} 提示：{tts_text}")
                                    except Exception as e:
                                        console_error(f"处理专家事件异常: {e}")
                                continue

                            # 常规预览流
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
                    console_error(f"❌ 节点 [{pi_id}] 通信异常: {e}")
                    await asyncio.sleep(3)

    def _handle_remote_voice(self, pi_id, data):
        """处理来自 Pi 的语音回传文本"""
        cmd_text = data.replace("PI_VOICE_COMMAND:", "")
        console_info(f"📩 收到节点 {pi_id} 语音指令: {cmd_text}")
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