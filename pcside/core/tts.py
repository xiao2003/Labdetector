#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/tts.py - TTS语音播报模块
"""

import threading
import sys
import os


class TTSManager:
    """TTS管理器，提供统一的语音播报接口"""

    def __init__(self):
        self.speaker = None
        self._init_tts()

    def _init_tts(self):
        """初始化TTS引擎"""
        try:
            # 尝试Windows SAPI
            if sys.platform == "win32":
                import win32com.client
                self.speaker = win32com.client.Dispatch("SAPI.SpVoice")
                for voice in self.speaker.GetVoices():
                    if "zh-CN" in voice.Id:
                        self.speaker.Voice = voice
                        break
                self.speaker.Volume = 100
                self.speaker.Rate = 0
                return
        except:
            pass

        try:
            # 尝试pyttsx3
            import pyttsx3
            self.speaker = pyttsx3.init()
            self.speaker.setProperty('rate', 150)
            self.speaker.setProperty('volume', 1.0)
            return
        except:
            pass

        try:
            # 尝试espeak（Linux）
            import shutil
            if shutil.which("espeak") is not None:
                self.speaker = "espeak"
                return
        except:
            pass

    def is_available(self) -> bool:
        """检查TTS是否可用"""
        return self.speaker is not None

    def speak_async(self, text: str):
        """异步语音播报"""

        def _speak():
            if not text or not self.speaker:
                return

            try:
                if sys.platform == "win32" and hasattr(self.speaker, "Speak"):
                    self.speaker.Speak(text)
                elif self.speaker == "espeak":
                    import subprocess
                    subprocess.Popen(["espeak", "-v", "zh", "-s", "150", text])
                elif hasattr(self.speaker, "say"):
                    self.speaker.say(text)
                    self.speaker.runAndWait()
            except Exception:
                pass

        threading.Thread(target=_speak, daemon=True).start()


# 全局TTS实例
_tts_manager = TTSManager()


def speak_async(text: str):
    """全局语音播报函数"""
    _tts_manager.speak_async(text)