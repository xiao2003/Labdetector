# piside/voice/recognizer.py
import vosk
import json
import os


class PiVoiceRecognizer:
    def __init__(self, model_path: str):
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Vosk模型路径不存在: {model_path}")

        # 加载本地模型
        self.model = vosk.Model(model_path)
        # 采样率需固定为 16000
        self.rec = vosk.KaldiRecognizer(self.model, 16000)

    def recognize_stream(self, data: bytes) -> str:
        """解析音频流数据"""
        if self.rec.AcceptWaveform(data):
            res = json.loads(self.rec.Result())
            return res.get("text", "").replace(" ", "")
        return ""

    def get_final_text(self) -> str:
        """获取最后一句识别结果"""
        res = json.loads(self.rec.FinalResult())
        return res.get("text", "").replace(" ", "")