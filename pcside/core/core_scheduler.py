import cv2
import time
import threading
import torch
import sys
import os
import json
import urllib.request
import urllib.error

# ==========================================
# 动态注入系统路径，确保能找到当前目录下的 logger.py
# ==========================================
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from logger import console_info, console_error, console_prompt, console_status


# ==========================================
# 模块 1：本地 Ollama 大语言模型对接专家
# ==========================================
class OllamaLLMExpert:
    """对接本地私有化大模型，处理通用知识问答与 RAG"""

    def __init__(self, model_name="qwen:7b", host="http://localhost:11434"):
        self.model_name = model_name
        self.api_url = f"{host}/api/generate"
        console_info(f"已挂载本地大模型接口: {model_name} (Ollama)")

    def chat(self, prompt: str):
        console_status("思考中...")
        payload = {
            "model": self.model_name,
            "prompt": f"你是一个专业的微纳米实验室AI管家。用户对你说：{prompt}。请简短、专业地回答。",
            "stream": False
        }
        try:
            req = urllib.request.Request(self.api_url, data=json.dumps(payload).encode('utf-8'),
                                         headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=15) as response:
                result = json.loads(response.read().decode('utf-8'))
                console_status("")  # 清除状态行
                console_prompt(f"\n[AI 管家]: {result.get('response', '')}\n")
        except urllib.error.URLError:
            console_status("")
            console_error("无法连接到本地 Ollama 服务，请确认 Ollama 客户端已启动且模型存在。")


# ==========================================
# 模块 2：仪器 OCR 识别专家 (动态加载)
# ==========================================
class EquipmentOCRExpert:
    """仪器仪表读数识别，极其消耗显存，采用动态按需加载"""

    def __init__(self):
        self.reader = None
        self.is_loaded = False

    def lazy_load(self):
        if not self.is_loaded:
            console_info("正在唤醒 [设备 OCR 识别专家] 入显存...")
            try:
                import easyocr
                # gpu=True 确保使用我们刚装好的 CUDA 环境
                self.reader = easyocr.Reader(['ch_sim', 'en'], gpu=torch.cuda.is_available())
                self.is_loaded = True
                console_info("OCR 模型已就绪，准备提取仪表读数。")
            except ImportError:
                console_error("未检测到 easyocr，请执行 pip install easyocr")

    def lazy_unload(self):
        if self.is_loaded:
            console_info("识别完成，正在释放 [OCR 专家] 显存...")
            self.reader = None
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            self.is_loaded = False

    def extract_text(self, frame):
        if self.is_loaded and self.reader is not None:
            # 执行真正的 OCR 推理
            results = self.reader.readtext(frame)
            text_extracted = " ".join([res[1] for res in results])
            if text_extracted.strip():
                console_prompt(f">>> [OCR 识别结果]: {text_extracted}")
            return text_extracted
        return None


# ==========================================
# 模块 3：微纳流体专家 (动态加载) & 安全专家 (常驻)
# ==========================================
class MicrofluidicContactAngleExpert:
    def __init__(self):
        self.model = None
        self.is_loaded = False

    def lazy_load(self):
        if not self.is_loaded:
            console_info("正在将 [微纳流体接触角分析专家] 调入显存...")
            time.sleep(1)  # 模拟模型加载耗时
            self.is_loaded = True
            console_info("接触角专家加载完毕，接管高精度视觉流。")

    def lazy_unload(self):
        if self.is_loaded:
            console_info("实验结束，释放 [接触角分析专家] 显存...")
            self.model = None
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            self.is_loaded = False

    def analyze(self, frame):
        if self.is_loaded:
            # 真实业务中在此执行 CV 处理并计算角度
            pass


class UnifiedSafetyExpert:
    def __init__(self):
        console_info("正在初始化 [通用安全防范专家] (常驻显存)...")
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

    def detect(self, frame):
        # 实时检测火焰/PPE/洒漏
        pass


# ==========================================
# 核心调度器：多模态分发引擎
# ==========================================
class LabMultiModalScheduler:
    def __init__(self):
        # 初始化各大专家
        self.llm_expert = OllamaLLMExpert()
        self.safety_expert = UnifiedSafetyExpert()
        self.contact_angle_expert = MicrofluidicContactAngleExpert()
        self.ocr_expert = EquipmentOCRExpert()

        # 视频调度状态机
        self.is_running = False
        self.frame_count = 0
        self.current_vision_task = "safety_only"  # 状态枚举：safety_only, contact_angle, ocr
        self.latest_frame = None

    def start_vision_stream(self, camera_id=0):
        self.is_running = True
        cap = cv2.VideoCapture(camera_id)
        console_info(f"视频流引擎启动，摄像头 ID: {camera_id}")

        while self.is_running and cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            self.latest_frame = frame
            self.frame_count += 1

            # 【策略A】安全底座：每 3 帧做一次安防监控 (不可中断)
            if self.frame_count % 3 == 0:
                self.safety_expert.detect(frame)

            # 【策略B】按需分配算力：根据状态机分发当前帧
            if self.current_vision_task == "contact_angle" and self.frame_count % 5 == 0:
                self.contact_angle_expert.analyze(frame)
            elif self.current_vision_task == "ocr" and self.frame_count % 10 == 0:
                # OCR 处理相对较慢，拉低抽帧率，或者在独立线程中执行单张照片的OCR
                self.ocr_expert.extract_text(frame)
                # 假设只识别一次就退出任务以节省资源
                self.current_vision_task = "safety_only"
                self.ocr_expert.lazy_unload()

            if self.frame_count >= 3000:
                self.frame_count = 0
                console_status("系统运行良好，多模态引擎持续监控中...")

        cap.release()
        console_info("视频流引擎已安全关闭。")

    def process_voice_command(self, recognized_text: str):
        """核心路由：意图识别与任务分发"""
        console_prompt(f"\n[🎤 听到语音]: '{recognized_text}'")

        # 1. 硬件/CV 控制意图拦截
        if "分析接触角" in recognized_text or "开始实验" in recognized_text:
            self.contact_angle_expert.lazy_load()
            self.current_vision_task = "contact_angle"
            console_prompt(">>> [系统执行]: 已将算力分配至微纳流体分析。")

        elif "停止分析" in recognized_text or "实验结束" in recognized_text:
            self.current_vision_task = "safety_only"
            self.contact_angle_expert.lazy_unload()
            console_prompt(">>> [系统执行]: 已恢复常规安全监控模式。")

        elif "读取仪表" in recognized_text or "看下读数" in recognized_text:
            self.ocr_expert.lazy_load()
            self.current_vision_task = "ocr"
            console_prompt(">>> [系统执行]: 正在对当前视野内设备进行文字提取...")

        # 2. 如果不是系统控制指令，则作为专业问题，抛给本地大语言模型
        else:
            # 开启子线程去请求大模型，防止阻塞主程序的语音监听
            threading.Thread(target=self.llm_expert.chat, args=(recognized_text,)).start()


# ==========================================
# 模拟入口
# ==========================================
if __name__ == "__main__":
    console_prompt("==================================================")
    console_prompt(" LabDetector V2.6 - 全模态算力调度中枢 (CUDA Enabled)")
    console_prompt("==================================================")

    scheduler = LabMultiModalScheduler()

    # 启动异步视觉引擎
    vision_thread = threading.Thread(target=scheduler.start_vision_stream)
    vision_thread.start()

    # --- 剧本模拟演练 ---
    time.sleep(2)
    # 场景 1: 日常问答 (交给 Ollama)
    scheduler.process_voice_command("如果氢氟酸洒在手套上应该怎么处理？")

    time.sleep(6)
    # 场景 2: 启动吃算力的实验 (卸载非必要显存，加载专属CV)
    scheduler.process_voice_command("管家，帮我开始分析接触角")

    time.sleep(4)
    # 场景 3: 临时需要读取仪表盘
    scheduler.process_voice_command("帮我看下读数是多少")

    time.sleep(5)
    # 场景 4: 实验结束
    scheduler.process_voice_command("实验结束")

    time.sleep(2)
    scheduler.is_running = False
    vision_thread.join()