#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
voice_interaction.py - 独立语音交互模块
提供唤醒词检测和语音对话功能
"""

import threading
import time
import os
import sys
import logging
from typing import Optional, Dict, Any, Callable

try:
    import speech_recognition as sr
    import pyaudio
    from queue import Queue
    import wave
    import numpy as np

    VOICE_INTERACTION_AVAILABLE = True
except ImportError:
    VOICE_INTERACTION_AVAILABLE = False


class VoiceInteractionConfig:
    """语音交互配置类"""

    def __init__(self):
        # 唤醒词配置
        self.wake_word = "小爱同学"  # 唤醒词
        self.wake_timeout = 10  # 唤醒后等待指令的超时时间（秒）
        self.wake_threshold = 0.01  # Sphinx唤醒词检测阈值

        # 语音识别配置
        self.silence_threshold = 500  # 静音阈值
        self.min_speech_duration = 0.5  # 最小语音持续时间（秒）
        self.max_speech_duration = 10  # 最大语音持续时间（秒）
        self.energy_threshold = 300  # 能量阈值，用于语音检测
        self.pause_threshold = 0.8  # 语音暂停阈值

        # 语音播报配置
        self.volume = 100  # 音量（0-100）
        self.rate = 0  # 语速（-10到10）

        # 系统配置
        self.auto_start = True  # 是否自动启动语音交互
        self.online_recognition = True  # 是否优先使用在线识别
        self.tts_engine = "system"  # TTS引擎类型：system/pyttsx3/espeak

        # 回调函数
        self.on_wake = None  # 唤醒回调
        self.on_command = None  # 命令处理回调
        self.on_ai_response = None  # AI回复回调
        self.on_stop_speech = None  # 停止当前语音播报的回调


class VoiceInteraction:
    """语音交互管理器 - 实现唤醒词检测和语音对话功能"""

    def __init__(self, config: Optional[VoiceInteractionConfig] = None):
        """
        初始化语音交互管理器
        Args:
            config: 可选的配置对象，使用默认配置如果未提供
        """
        self.config = config or VoiceInteractionConfig()
        self.recognizer = sr.Recognizer()
        self.microphone = sr.Microphone()
        self.is_active = False  # 是否处于激活状态（等待指令）
        self.interaction_thread = None
        self.stop_event = threading.Event()
        self.processing = False
        self.last_wake_time = 0
        self.tts_speaker = None
        self.ai_backend = None
        self._logger = self._setup_logger()

        # 配置语音识别
        self._configure_recognizer()

    def _setup_logger(self):
        """设置模块专用的日志记录器"""
        logger = logging.getLogger("voice_interaction")
        logger.setLevel(logging.INFO)
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        return logger

    def _configure_recognizer(self):
        """配置语音识别器参数"""
        self.recognizer.energy_threshold = self.config.energy_threshold
        self.recognizer.dynamic_energy_threshold = True
        self.recognizer.pause_threshold = self.config.pause_threshold

    def set_ai_backend(self, backend: str, model: str = "", api_key: Optional[str] = None):
        """
        设置AI后端用于处理语音指令
        Args:
            backend: "ollama" 或 "qwen"
            model: 模型名称（可选）
            api_key: API密钥（用于Qwen）
        """
        self.ai_backend = {
            "type": backend,
            "model": model,
            "api_key": api_key
        }
        self._logger.info(f"AI后端设置为: {backend}, 模型: {model}")

    def set_config(self, **kwargs):
        """
        动态更新配置
        Args:
            **kwargs: 配置参数
        """
        for key, value in kwargs.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)
                self._logger.info(f"配置更新: {key} = {value}")

        # 重新配置识别器
        if any(k in kwargs for k in ["energy_threshold", "pause_threshold"]):
            self._configure_recognizer()

    def start(self) -> bool:
        """
        启动语音交互服务
        Returns:
            bool: 是否成功启动
        """
        if not VOICE_INTERACTION_AVAILABLE:
            self._logger.warning("语音交互功能不可用，缺少依赖库（speech_recognition, pyaudio）")
            return False

        if self.interaction_thread and self.interaction_thread.is_alive():
            self._logger.info("语音交互服务已在运行")
            return True

        # 检查麦克风是否可用
        try:
            with self.microphone as source:
                self.recognizer.adjust_for_ambient_noise(source, duration=1)
            self._logger.info(f"语音交互服务已启动，唤醒词: '{self.config.wake_word}'")
        except Exception as e:
            self._logger.error(f"麦克风初始化失败: {str(e)}")
            return False

        # 初始化TTS
        if not self._init_tts():
            self._logger.warning("TTS初始化失败，语音播报功能将不可用")

        self.stop_event.clear()
        self.interaction_thread = threading.Thread(target=self._interaction_loop, daemon=True)
        self.interaction_thread.start()
        return True

    def stop(self):
        """停止语音交互服务"""
        self.stop_event.set()
        if self.interaction_thread and self.interaction_thread.is_alive():
            self.interaction_thread.join(timeout=2.0)
        self._logger.info("语音交互服务已停止")

    def _init_tts(self) -> bool:
        """
        初始化TTS语音引擎
        Returns:
            bool: 是否成功初始化
        """
        try:
            # 尝试使用系统TTS
            if self.config.tts_engine == "system" and sys.platform == "win32":
                import win32com.client
                self.tts_speaker = win32com.client.Dispatch("SAPI.SpVoice")
                for voice in self.tts_speaker.GetVoices():
                    if "zh-CN" in voice.Id:
                        self.tts_speaker.Voice = voice
                        break
                self.tts_speaker.Volume = self.config.volume
                self.tts_speaker.Rate = self.config.rate
                return True

            # 尝试使用pyttsx3
            elif self.config.tts_engine in ["pyttsx3", "system"]:
                try:
                    import pyttsx3
                    engine = pyttsx3.init()
                    engine.setProperty('rate', 150 + (self.config.rate * 10))
                    engine.setProperty('volume', self.config.volume / 100.0)
                    self.tts_speaker = engine
                    return True
                except Exception:
                    pass

            # 尝试使用espeak（Linux）
            elif self.config.tts_engine in ["espeak", "system"] and sys.platform.startswith("linux"):
                import shutil
                if shutil.which("espeak") is not None:
                    self.tts_speaker = "espeak"
                    return True

        except Exception as e:
            self._logger.error(f"TTS初始化错误: {str(e)}")

        self._logger.warning("未找到可用的TTS引擎")
        return False

    def speak(self, text: str):
        """
        语音播报
        Args:
            text: 要播报的文本
        """

        def _speak():
            if not text:
                return

            try:
                if self.tts_speaker and sys.platform == "win32":
                    # Windows系统TTS
                    self.tts_speaker.Speak(text)
                elif self.tts_speaker == "espeak":
                    # Linux espeak
                    import subprocess
                    subprocess.Popen(["espeak", "-v", "zh", "-s", "150", text])
                elif hasattr(self.tts_speaker, "say"):
                    # pyttsx3
                    self.tts_speaker.say(text)
                    self.tts_speaker.runAndWait()
            except Exception as e:
                self._logger.error(f"语音播报失败: {str(e)}")

        threading.Thread(target=_speak, daemon=True).start()

    def stop_current_speech(self):
        """停止当前正在播报的语音"""
        if self.config.on_stop_speech:
            try:
                self.config.on_stop_speech()
            except Exception as e:
                self._logger.error(f"停止语音播报失败: {str(e)}")

    def _interaction_loop(self):
        """语音交互主循环 - 持续监听唤醒词和指令"""
        # 只在启动时输出一次日志
        self._logger.info(f"语音交互服务已启动，唤醒词: '{self.config.wake_word}'")

        while not self.stop_event.is_set():
            try:
                with self.microphone as source:
                    # 检查是否超时
                    current_time = time.time()
                    if self.is_active and (current_time - self.last_wake_time) > self.config.wake_timeout:
                        self.is_active = False
                        # 不输出等待唤醒信息，保持静默

                    if not self.is_active:
                        # 监听唤醒词
                        try:
                            audio = self.recognizer.listen(
                                source,
                                timeout=5,
                                phrase_time_limit=3
                            )

                            # 尝试识别唤醒词（使用离线识别）
                            try:
                                # 使用pocketsphinx进行关键词检测
                                text = self.recognizer.recognize_sphinx(
                                    audio,
                                    keyword_entries=[(self.config.wake_word, 1.0, self.config.wake_threshold)]
                                )
                                if self.config.wake_word in text:
                                    self._handle_wake_word()
                            except sr.UnknownValueError:
                                # 未识别到关键词，保持静默
                                continue
                            except sr.RequestError:
                                continue
                        except sr.WaitTimeoutError:
                            # 超时，继续循环，保持静默
                            continue
                    else:
                        # 已唤醒，等待指令
                        try:
                            audio = self.recognizer.listen(
                                source,
                                timeout=5,
                                phrase_time_limit=self.config.max_speech_duration
                            )

                            # 识别语音指令
                            try:
                                # 优先使用Google在线识别（如果配置允许）
                                if self.config.online_recognition:
                                    text = self.recognizer.recognize_google(audio, language="zh-CN")
                                    self._process_command(text)
                                else:
                                    raise sr.RequestError("在线识别已禁用")
                            except sr.UnknownValueError:
                                self.speak("抱歉，我没有听清楚")
                                self.is_active = False
                            except sr.RequestError:
                                # Google识别失败，尝试使用Sphinx离线识别
                                try:
                                    text = self.recognizer.recognize_sphinx(audio, language="zh-cn")
                                    self._process_command(text)
                                except sr.UnknownValueError:
                                    self.speak("抱歉，我没有听清楚")
                                    self.is_active = False
                        except sr.WaitTimeoutError:
                            self.is_active = False
            except Exception as e:
                # 只在发生错误时输出一次日志
                self._logger.error(f"语音交互错误: {str(e)}")
                time.sleep(1)

    def _handle_wake_word(self):
        """处理唤醒事件"""
        self.is_active = True
        self.last_wake_time = time.time()
        # 停止当前正在播报的语音
        self.stop_current_speech()
        # 播放提示音
        self.speak("我在")

        # 触发唤醒回调
        if self.config.on_wake:
            try:
                self.config.on_wake()
            except Exception as e:
                self._logger.error(f"唤醒回调执行失败: {str(e)}")

    def _process_command(self, command):
        """处理语音指令"""
        self.is_active = False  # 重置激活状态

        # 触发命令处理回调
        if self.config.on_command:
            try:
                if self.config.on_command(command):
                    return  # 如果回调处理了命令，不再继续处理
            except Exception as e:
                self._logger.error(f"命令回调执行失败: {str(e)}")

        # 检查特殊指令
        if "退出" in command or "关闭" in command or "停止" in command:
            self.speak("好的，正在退出系统")
            # 通过回调通知主程序
            if self.config.on_ai_response:
                self.config.on_ai_response("exit")
            return

        if "切换" in command and ("模式" in command or "摄像头" in command):
            self.speak("已切换模式")
            # 通过回调通知主程序
            if self.config.on_ai_response:
                self.config.on_ai_response("switch_mode")
            return

        if "模型" in command and "切换" in command:
            self.speak("模型切换功能暂未实现")
            return

        # 将指令作为普通问题发送给AI处理
        self._process_with_ai(command)

    def _process_with_ai(self, text):
        """使用AI处理文本并返回语音回复"""
        # 如果没有设置AI后端，直接返回错误
        if not self.ai_backend:
            self.speak("AI后端未配置，请先设置AI后端")
            return

        try:
            response = None
            # 处理不同类型的AI后端
            if self.ai_backend["type"] == "qwen":
                try:
                    from qwen_integration import QwenAnalyzer
                    import os

                    # 获取API密钥
                    api_key = self.ai_backend["api_key"] or os.getenv("QWEN_API_KEY")
                    if not api_key:
                        import configparser
                        config = configparser.ConfigParser()
                        if config.read('config.ini') and 'qwen' in config and 'api_key' in config['qwen']:
                            api_key = config['qwen']['api_key']

                    if api_key:
                        qwen_analyzer = QwenAnalyzer(api_key)
                        # 使用Qwen的文本对话功能
                        response = qwen_analyzer.chat(text)
                    else:
                        response = "Qwen API密钥未配置"
                except ImportError:
                    response = "Qwen模块缺失"
                except Exception as e:
                    response = f"Qwen处理出错: {str(e)[:50]}"

            elif self.ai_backend["type"] == "ollama":
                try:
                    import requests
                    # 检查是否有纯文本模型
                    text_model = self.ai_backend["model"].replace("llava", "qwen-turbo")
                    if "llama" not in text_model and "qwen" not in text_model:
                        text_model = "qwen:1.8b-chat"

                    payload = {
                        "model": text_model,
                        "prompt": text,
                        "stream": False
                    }
                    resp = requests.post(
                        "http://localhost:11434/api/generate",
                        json=payload,
                        timeout=20
                    )
                    if resp.status_code == 200:
                        response = resp.json()["response"].strip()
                    else:
                        response = "Ollama处理失败"
                except Exception as e:
                    response = f"Ollama处理出错: {str(e)[:50]}"

            # 处理响应
            if response:
                # 限制回复长度
                response = response[:150]
                # 语音播报回复
                self.speak(response)

                # 触发AI回复回调
                if self.config.on_ai_response:
                    try:
                        self.config.on_ai_response(response)
                    except Exception as e:
                        self._logger.error(f"AI回复回调执行失败: {str(e)}")
            else:
                self.speak("抱歉，没有获取到回复")

        except Exception as e:
            error_msg = f"处理过程中出错: {str(e)[:50]}"
            self._logger.error(error_msg)
            self.speak("抱歉，处理您的请求时出错")


def get_voice_interaction_instance(config: Optional[VoiceInteractionConfig] = None) -> VoiceInteraction:
    """
    获取语音交互单例实例
    Args:
        config: 可选的配置对象
    Returns:
        VoiceInteraction: 语音交互实例
    """
    if not hasattr(get_voice_interaction_instance, "_instance"):
        get_voice_interaction_instance._instance = VoiceInteraction(config)
    return get_voice_interaction_instance._instance


def is_voice_interaction_available() -> bool:
    """
    检查语音交互功能是否可用
    Returns:
        bool: 是否可用
    """
    return VOICE_INTERACTION_AVAILABLE