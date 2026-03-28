# pi/voice/interaction.py
import time
from .recognizer import PiVoiceRecognizer


class PiVoiceInteraction:
    def __init__(self, recognizer: PiVoiceRecognizer, wake_word="小爱同学", wake_aliases=None):
        self.recognizer = recognizer
        self.wake_word = str(wake_word or "小爱同学")
        self.wake_aliases = [str(item).strip() for item in (wake_aliases or []) if str(item).strip()]
        self.is_active = False
        self.last_active_time = 0
        self.last_wake_time = 0
        self.timeout = 10  # 唤醒后10秒没指令则回退
        self.stop_commands = ("停止播报", "停止说话", "别说了", "闭嘴", "停一下", "先别播报")

    @staticmethod
    def _normalize_text(text: str) -> str:
        normalized = str(text or "").strip().lower()
        for token in (" ", "，", "。", "！", "？", ",", ".", "!", "?", "：", ":", "；", ";", "\n", "\r", "\t"):
            normalized = normalized.replace(token, "")
        return normalized

    def _wake_matches(self, text: str) -> bool:
        normalized = self._normalize_text(text)
        if not normalized:
            return False
        aliases = list(self.wake_aliases)
        if self.wake_word:
            aliases.insert(0, self.wake_word)
        for alias in aliases:
            alias_normalized = self._normalize_text(alias)
            if alias_normalized and alias_normalized in normalized:
                return True
        return False

    def _is_stop_command(self, text: str) -> bool:
        normalized = self._normalize_text(text)
        return any(self._normalize_text(keyword) in normalized for keyword in self.stop_commands)

    def process_audio(self, audio_data: bytes):
        """处理每一帧音频数据"""
        text = self.recognizer.recognize_stream(audio_data)
        if not text:
            return None

        if self._is_stop_command(text):
            self.is_active = False
            return "EVENT:STOP_TTS"

        # 状态机逻辑
        if not self.is_active:
            # 待机状态：找唤醒词
            if self._wake_matches(text):
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
