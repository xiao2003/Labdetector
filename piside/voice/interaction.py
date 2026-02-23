# piside/voice/interaction.py
import time
from .recognizer import PiVoiceRecognizer


class PiVoiceInteraction:
    def __init__(self, recognizer: PiVoiceRecognizer, wake_word="小爱同学"):
        self.recognizer = recognizer
        self.wake_word = wake_word
        self.is_active = False
        self.last_active_time = 0
        self.timeout = 10  # 唤醒后10秒没指令则回退

    def process_audio(self, audio_data: bytes):
        """处理每一帧音频数据"""
        text = self.recognizer.recognize_stream(audio_data)
        if not text:
            return None

        # 状态机逻辑
        if not self.is_active:
            # 待机状态：找唤醒词
            if self.wake_word in text:
                self.is_active = True
                self.last_wake_time = time.time()
                return "EVENT:WOKEN"  # 触发唤醒事件
        else:
            # 激活状态：捕捉指令
            if (time.time() - self.last_wake_time) > self.timeout:
                self.is_active = False
                return "EVENT:TIMEOUT"

            # 返回识别到的有效指令文本
            return f"CMD_TEXT:{text}"

        return None