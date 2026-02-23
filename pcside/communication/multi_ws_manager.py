# pcside/communication/multi_ws_manager.py
import asyncio
import websockets
import numpy as np
import cv2
from pcside.core.logger import console_info, console_error


class MultiPiManager:
    def __init__(self, pi_dict: dict):
        self.pi_dict = pi_dict
        self.frame_buffers = {pid: None for pid in pi_dict}
        self.send_queues = {pid: asyncio.Queue() for pid in pi_dict}
        self.running = True

        # ==========================================
        # ★ 核心升级：动态带宽均衡策略
        # ==========================================
        num_nodes = len(pi_dict)
        # 总带宽限制在 30FPS，由所有节点平分
        self.target_fps = max(1.0, 30.0 / num_nodes) if num_nodes > 0 else 30.0

    async def _node_handler(self, pi_id, ip):
        uri = f"ws://{ip}:8001"
        while self.running:
            try:
                async with websockets.connect(uri, ping_interval=None) as ws:
                    console_info(f"🔗 节点 [{pi_id}] ({ip}) 握手成功")

                    # 握手后的第一件事：强制树莓派修改摄像头发送频率！
                    control_cmd = f"CMD:SET_FPS:{self.target_fps}"
                    await ws.send(control_cmd)
                    console_info(f"🎛️ 已向节点 [{pi_id}] 下发动态帧率调度: {self.target_fps:.1f} FPS")

                    async def recv_stream_task():
                        async for data in ws:
                            if not self.running: break
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
                    console_error(f"❌ 节点 [{pi_id}] 通信异常，3秒后重连")
                    await asyncio.sleep(3)

    async def start(self):
        tasks = [self._node_handler(pid, ip) for pid, ip in self.pi_dict.items()]
        await asyncio.gather(*tasks)

    def send_to_node(self, pi_id, text):
        if pi_id in self.send_queues:
            self.send_queues[pi_id].put_nowait(text)

    def stop(self):
        self.running = False