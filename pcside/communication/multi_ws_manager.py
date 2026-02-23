# pcside/communication/multi_ws_manager.py
import asyncio
import websockets
import numpy as np
import cv2
# ★ 核心修正 1：使用绝对包路径引用 core，确保 setup.py 安装后能正确寻址
from pcside.core.logger import console_info, console_error


class MultiPiManager:
    def __init__(self, pi_dict: dict):
        """
        pi_dict: 拓扑字典，例如 {"1": "192.168.1.10", "2": "192.168.1.11"}
        """
        self.pi_dict = pi_dict
        self.frame_buffers = {pid: None for pid in pi_dict}
        self.send_queues = {pid: asyncio.Queue() for pid in pi_dict}
        self.running = True

    async def _node_handler(self, pi_id, ip):
        """处理单个树莓派节点的长连接"""
        uri = f"ws://{ip}:8001"
        while self.running:
            try:
                # 调高 ping_interval 避免实验内弱网导致的误断连
                async with websockets.connect(uri, ping_interval=None) as ws:
                    console_info(f"🔗 节点 [{pi_id}] ({ip}) 已成功建立双向通道")

                    # ★ 核心修正 2：确保函数定义与下面 gather 调用中的名称完全一致
                    async def recv_stream_task():
                        """接收视频流任务"""
                        async for data in ws:
                            if not self.running: break
                            arr = np.frombuffer(data, np.uint8)
                            frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                            if frame is not None:
                                # 更新对应 ID 的画面缓存
                                self.frame_buffers[pi_id] = frame

                    async def send_command_task():
                        """发送指令任务"""
                        while self.running:
                            # 从当前节点的专属异步队列获取消息
                            msg = await self.send_queues[pi_id].get()
                            await ws.send(msg)

                    # 并发运行接收和发送任务
                    await asyncio.gather(recv_stream_task(), send_command_task())
            except Exception as e:
                if self.running:
                    console_error(f"❌ 节点 [{pi_id}] 连接异常: {str(e)[:40]}，3秒后重连")
                    await asyncio.sleep(3)

    async def start(self):
        """并发启动所有配置在 pi_dict 中的节点协程"""
        tasks = [self._node_handler(pid, ip) for pid, ip in self.pi_dict.items()]
        await asyncio.gather(*tasks)

    def send_to_node(self, pi_id, text):
        """
        外部主线程调用：定向分发指令给指定 ID 的树莓派
        """
        if pi_id in self.send_queues:
            # 使用 put_nowait 因为主循环是同步运行的，不需要 await
            self.send_queues[pi_id].put_nowait(text)

    def stop(self):
        """停止所有连接任务"""
        self.running = False