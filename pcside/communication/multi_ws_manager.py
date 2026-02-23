# pcside/communication/multi_ws_manager.py
import asyncio
import websockets
import numpy as np
import cv2
# 修正：必须加上 pcside 前缀，且确保 setup.py 已安装
from pcside.core.logger import console_info, console_error


class MultiPiManager:
    def __init__(self, pi_dict: dict):
        self.pi_dict = pi_dict
        self.frame_buffers = {pid: None for pid in pi_dict}
        self.send_queues = {pid: asyncio.Queue() for pid in pi_dict}
        self.running = True

    async def _node_handler(self, pi_id, ip):
        """处理单个树莓派节点的长连接"""
        uri = f"ws://{ip}:8001"
        while self.running:
            try:
                # 调优：取消 ping 超时限制，防止实验环境干扰
                async with websockets.connect(uri, ping_interval=None) as ws:
                    console_info(f"🔗 节点 [{pi_id}] ({ip}) 通道建立成功")

                    # 修正：函数名统一为 recv_stream_task
                    async def recv_stream_task():
                        async for data in ws:
                            if not self.running: break
                            arr = np.frombuffer(data, np.uint8)
                            frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                            if frame is not None:
                                self.frame_buffers[pi_id] = frame

                    # 修正：函数名统一为 send_command_task，解决“未使用”警告
                    async def send_command_task():
                        while self.running:
                            msg = await self.send_queues[pi_id].get()
                            await ws.send(msg)

                    # 修正：gather 内部调用名必须与上方定义完全一致
                    await asyncio.gather(recv_stream_task(), send_command_task())
            except Exception as e:
                if self.running:
                    console_error(f"❌ 节点 [{pi_id}] 异常: {str(e)[:30]}，3秒后重连")
                    await asyncio.sleep(3)

    async def start(self):
        """并发启动所有配置在 pi_dict 中的节点"""
        tasks = [self._node_handler(pid, ip) for pid, ip in self.pi_dict.items()]
        await asyncio.gather(*tasks)

    def send_to_node(self, pi_id, text):
        """定向分发指令"""
        if pi_id in self.send_queues:
            self.send_queues[pi_id].put_nowait(text)

    def stop(self):
        self.running = False