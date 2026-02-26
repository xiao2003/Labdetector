import cv2
import os
from pcside.core.base_expert import BaseExpert
from pcside.core.logger import console_info, console_error

try:
    from ultralytics import YOLO
    import torch

    HAS_YOLO = True
except ImportError:
    HAS_YOLO = False


class PPEExpert(BaseExpert):
    def __init__(self):
        super().__init__()
        self.model = None
        # 动态获取当前 ppe_expert.py 所在的文件夹路径
        current_dir = os.path.dirname(os.path.abspath(__file__))
        # 将模型路径强制绑定到该专家目录下
        self.model_path = os.path.join(current_dir, "yolov8n.pt")
        self.force_cpu = False  # 自愈降级标志位

    @property
    def expert_name(self):
        return "个人防护装备(PPE)规范专家"

    def get_edge_policy(self):
        return {
            "event_name": "Motion_Alert",
            "trigger": ["Pixel_Motion_Active"],
            "crop_strategy": "motion_bounding_box",
            "padding": 0.5
        }

    def match_event(self, event_name):
        return event_name == "Motion_Alert"

    def analyze(self, frame, context):
        if not HAS_YOLO:
            return ""

        if self.model is None:
            try:
                console_info(f"[{self.expert_name}] 正在加载 YOLO 轻量级模型 (自适应设备)...")
                # ★ 如果 force_cpu 为真，则直接在初始化时就指定设备为 cpu
                device_str = 'cpu' if self.force_cpu else None
                self.model = YOLO(self.model_path, task='detect')

                # 如果尚未强制降级，我们尝试进行一次极简的“热身”推理，用来测试驱动是否兼容
                if not self.force_cpu:
                    try:
                        # 随便创建一个 1x1 的空白图像进行热身测试
                        import numpy as np
                        dummy_img = np.zeros((64, 64, 3), dtype=np.uint8)
                        _ = self.model(dummy_img, verbose=False)
                    except Exception as e:
                        err_msg = str(e)
                        if "CUDA" in err_msg or "PTX" in err_msg or "device-side assert" in err_msg:
                            console_error(
                                f"[{self.expert_name}] 初始化时发现底层 CUDA 驱动兼容性异常，永久降级至 CPU 运行...")
                            self.force_cpu = True
                            # 重新以 CPU 模式加载模型
                            self.model = YOLO(self.model_path, task='detect')
            except Exception as e:
                console_error(f"[{self.expert_name}] YOLO加载失败: {e}")
                return ""

        try:
            # 运行快速目标检测 (verbose=False 避免控制台刷屏)
            # 注意：初始化时如果锁定了 CPU，这里的模型实例就已经是运行在 CPU 上的了
            device_choice = 'cpu' if self.force_cpu else None
            results = self.model(frame, verbose=False, conf=0.5, device=device_choice)

            # 提取检测到的类别
            detected_classes = []
            for r in results:
                for c in r.boxes.cls:
                    detected_classes.append(self.model.names[int(c)])

            # 核心业务逻辑
            if 'person' in detected_classes:
                # 伪代码：如果你训练了裸手检测
                if 'bare_hands' in detected_classes:
                    return "严重警告：检测到人员操作时未佩戴丁腈手套，请立即规范穿戴！"
                return ""

            return ""

        except Exception as e:
            err_msg = str(e)
            # 捕获由于 PyTorch/CUDA 驱动版本不匹配导致的底层 PTX 或 CUDA 错误
            if "CUDA" in err_msg or "PTX" in err_msg or "device-side assert" in err_msg:
                if not self.force_cpu:
                    console_error(
                        f"[{self.expert_name}] 发现底层 CUDA 驱动兼容性异常，触发自愈机制：正在自动降级至 CPU 运行...")
                    self.force_cpu = True
                    # 清理损坏的 GPU 上下文，重新加载到 CPU
                    self.model = YOLO(self.model_path, task='detect')
                    return ""  # 本次推理跳过，下一次将稳定运行

            # 其他非驱动类错误正常抛出，交给 ExpertManager 拦截
            raise e