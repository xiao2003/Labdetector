import asyncio
import websockets
import numpy as np
import cv2
from core.logger import console_info, console_error


class MultiPiManager:
    def __init__(self, pi_dict: dict):
        self.pi_dict = pi_dict  # {"1": "192.168.1.10", ...}
        self.frame_buffers = {pid: None for pid in pi_dict}
        self.send_queues = {pid: asyncio.Queue() for pid in pi_dict}
        self.running = True

    async def _node_handler(self, pi_id, ip):
        """处理单个树莓派节点的长连接"""
        uri = f"ws://{ip}:8001"
        while self.running:
            try:
                async with websockets.connect(uri, ping_interval=None) as ws:
                    console_info(f"🔗 节点 [{pi_id}] ({ip}) 已成功建立双向通道")

                    async def recv_video():
                        async for data in ws:
                            arr = np.frombuffer(data, np.uint8)
                            frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                            if frame is not None:
                                # 更新对应 ID 的画面缓存
                                self.frame_buffers[pi_id] = frame

                    async def send_text():
                        while self.running:
                            msg = await self.send_queues[pi_id].get()
                            await ws.send(msg)

                    await asyncio.gather(recv_video(), send_task())
            except Exception as e:
                if self.running:
                    console_error(f"❌ 节点 [{pi_id}] 断连: {str(e)[:30]}，3秒后重连")
                    await asyncio.sleep(3)

    async def start(self):
        """并发启动所有节点的协程"""
        tasks = [self._node_handler(pid, ip) for pid, ip in self.pi_dict.items()]
        await asyncio.gather(*tasks)

    def send_to_node(self, pi_id, text):
        """主线程定向分发指令"""
        if pi_id in self.send_queues:
            self.send_queues[pi_id].put_nowait(text)

    def stop(self):
        self.running = False