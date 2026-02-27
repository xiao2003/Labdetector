import threading
import time
import cv2
import os

from pcside.core.base_expert import BaseExpert
from pcside.core.logger import console_info
from pcside.core.ai_backend import analyze_image

# 1. 尝试引入 RAG 引擎
try:
    from pcside.knowledge_base.rag_engine import RAGEngine
except ImportError:
    RAGEngine = None

# 2. 尝试引入 YOLO (用于支持 PC 本机摄像头模式)
try:
    from ultralytics import YOLO
except ImportError:
    YOLO = None


class GeneralSafetyExpert(BaseExpert):
    def __init__(self):
        super().__init__()
        # 违规状态记录器
        self.violation_states = {}
        self.rag = RAGEngine() if RAGEngine else None

        # 动态定位 YOLO 专属模型目录
        if YOLO:
            console_info(f"[{self.expert_name}] 正在加载本地 YOLO 模型...")
            try:
                # 获取当前脚本所在绝对路径 (即 pcside/experts)
                current_dir = os.path.dirname(os.path.abspath(__file__))
                # 拼接出专门的模型文件夹路径
                model_dir = os.path.join(current_dir, "model")

                # 智能容错：如果目录不存在则自动创建
                if not os.path.exists(model_dir):
                    os.makedirs(model_dir, exist_ok=True)
                    console_info(f"[{self.expert_name}] 已自动创建模型存放目录: {model_dir}")

                # 指定优雅目录下的模型文件
                model_path = os.path.join(model_dir, "yolov8n.pt")
                self.model = YOLO(model_path)
            except Exception as e:
                console_info(f"本地 YOLO 加载失败: {e}")
                self.model = None
        else:
            self.model = None

    @property
    def expert_name(self) -> str:
        return "通用安防与RAG归档专家"

    def get_edge_policy(self) -> dict:
        return {}

    def match_event(self, event_name: str) -> bool:
        # 兼容树莓派("安防违规") 和 本机摄像头("Motion_Alert")
        return "安防违规" in event_name or event_name == "Motion_Alert"

    def analyze(self, frame, context) -> str:
        event_name = context.get("event_name", "")
        event_desc = context.get("event_desc", "在实验台使用手机")

        # 兼容 PC 本机摄像头模式：自己跑 YOLO
        if event_name == "Motion_Alert" and self.model:
            results = self.model(frame, verbose=False, conf=0.4)
            detected = []
            annotated_frame = frame.copy()
            for r in results:
                for box in r.boxes:
                    cls_name = self.model.names[int(box.cls[0])]
                    detected.append(cls_name)
                    # 画框
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), (0, 0, 255), 2)
                    cv2.putText(annotated_frame, cls_name, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

            # 判断逻辑
            if "person" in detected and "cell phone" in detected:
                event_desc = "违规在实验台使用手机"
                cv2.imwrite("debug_yolo_trigger.jpg", annotated_frame)  # 保存调试图
            else:
                return ""  # 未违规，静默

        # TTS 状态机
        current_time = time.time()
        state = self.violation_states.get(event_desc, {"first_seen": current_time, "last_alert": 0, "count": 0})

        tts_alert = ""
        if state["count"] == 0:
            console_info(f"[{self.expert_name}] 成功拦截到事件，开始首次报警...")
            tts_alert = f"警告：已检测到{event_desc}，请立即规范操作！"
            state["last_alert"] = current_time
            state["count"] += 1
            # 首次违规，触发 RAG 归档
            self._async_log_to_llm(frame, event_desc)

        elif current_time - state["last_alert"] > 30.0:
            console_info(f"[{self.expert_name}] 违规未解除，触发再次报警...")
            tts_alert = f"严重警告：您仍在{event_desc}，此行为高度危险，请立即停止！"
            state["last_alert"] = current_time
            state["count"] += 1

        self.violation_states[event_desc] = state
        return tts_alert

    def _async_log_to_llm(self, frame, event_desc):
        def task():
            rag_context = "暂无相关安全规范。"
            if self.rag:
                try:
                    rag_context = self.rag.query(f"关于'{event_desc}'的实验室安全管理规定与惩罚措施")
                except Exception as e:
                    console_info(f"RAG 检索失败: {e}")

            prompt = f"""
            系统触发了安防告警：'{event_desc}'。
            【实验室规范参考】：{rag_context}
            请结合上方规范和当前画面，生成一段约60字的专业实验室安全违规记录，说明潜在危害。
            """
            try:
                log_result = analyze_image(frame, model="qwen-vl-max", prompt=prompt)
                console_info(f"\n[AI for Science 智能日志归档] {log_result}\n")
            except Exception as e:
                pass

        threading.Thread(target=task, daemon=True).start()