#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Text-to-speech manager with observable backend selection."""

from __future__ import annotations

import shutil
import subprocess
import sys
import threading
from typing import Any

from pc.core.logger import console_error, console_info


class TTSManager:
    """Provide a small cross-platform TTS wrapper with debug-friendly logs."""

    def __init__(self) -> None:
        self.speaker: Any | None = None
        self.backend_name = "none"
        self._speak_lock = threading.Lock()
        self._init_tts()

    def _init_tts(self) -> None:
        try:
            if sys.platform == "win32":
                import win32com.client

                speaker = win32com.client.Dispatch("SAPI.SpVoice")
                for voice in speaker.GetVoices():
                    if "zh-CN" in str(getattr(voice, "Id", "")):
                        speaker.Voice = voice
                        break
                speaker.Volume = 100
                speaker.Rate = 0
                self.speaker = speaker
                self.backend_name = "sapi"
                console_info("[TTS] 已启用 Windows SAPI 语音引擎")
                return
        except Exception as exc:
            console_error(f"[TTS] Windows SAPI 初始化失败: {exc}")

        try:
            import pyttsx3

            speaker = pyttsx3.init()
            speaker.setProperty("rate", 150)
            speaker.setProperty("volume", 1.0)
            self.speaker = speaker
            self.backend_name = "pyttsx3"
            console_info("[TTS] 已启用 pyttsx3 语音引擎")
            return
        except Exception as exc:
            console_error(f"[TTS] pyttsx3 初始化失败: {exc}")

        try:
            if shutil.which("espeak") is not None:
                self.speaker = "espeak"
                self.backend_name = "espeak"
                console_info("[TTS] 已启用 espeak 语音引擎")
                return
        except Exception as exc:
            console_error(f"[TTS] espeak 检测失败: {exc}")

        self.speaker = None
        self.backend_name = "none"
        console_error("[TTS] 未检测到可用语音引擎，播报功能不可用")

    def is_available(self) -> bool:
        return self.speaker is not None

    def stop(self) -> None:
        try:
            if hasattr(self.speaker, "stop"):
                self.speaker.stop()
        except Exception:
            pass

    @staticmethod
    def _build_sapi_speaker() -> Any:
        import win32com.client

        speaker = win32com.client.Dispatch("SAPI.SpVoice")
        for voice in speaker.GetVoices():
            if "zh-CN" in str(getattr(voice, "Id", "")):
                speaker.Voice = voice
                break
        speaker.Volume = 100
        speaker.Rate = 0
        return speaker

    def speak_async(self, text: str) -> None:
        def _speak() -> None:
            message = str(text or "").strip()
            if not message:
                console_error("[TTS] 收到空文本，已跳过播报")
                return
            if not self.speaker:
                console_error(f"[TTS] 无可用语音引擎，无法播报: {message}")
                return

            try:
                console_info(f"[TTS] 使用 {self.backend_name} 播报: {message}")
                with self._speak_lock:
                    if sys.platform == "win32" and self.backend_name == "sapi":
                        try:
                            import pythoncom

                            pythoncom.CoInitialize()
                            try:
                                speaker = self._build_sapi_speaker()
                                speaker.Speak(message)
                            finally:
                                pythoncom.CoUninitialize()
                        except Exception as exc:
                            console_error(f"[TTS] SAPI 子线程播报失败: {exc}")
                    elif self.speaker == "espeak":
                        subprocess.Popen(["espeak", "-v", "zh", "-s", "150", message])
                    elif hasattr(self.speaker, "say"):
                        self.speaker.say(message)
                        self.speaker.runAndWait()
                    else:
                        console_error("[TTS] 当前语音引擎不支持播报接口")
            except Exception as exc:
                console_error(f"[TTS] 播报失败: {exc}")

        threading.Thread(target=_speak, daemon=True, name="TTSPlayback").start()


_tts_manager = TTSManager()


def speak_async(text: str) -> None:
    _tts_manager.speak_async(text)


def stop_tts() -> None:
    _tts_manager.stop()
