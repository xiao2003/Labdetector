#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/voice_interaction.py - 语音交互模块
"""

import threading
import time
import os
import sys
from typing import Optional, Callable

# 尝试导入核心模块，处理可能的导入错误
try:
    # 尝试相对导入
    from .logger import console_info, console_error
except ImportError:
    try:
        # 尝试绝对导入
        from core.logger import console_info, console_error
    except ImportError:
        # 定义简单的替代函数
        def console_info(text: str):
            print(f"[INFO] {text}")


        def console_error(text: str):
            import time
            print(f"\033[91m{time.strftime('%Y-%m-%d %H:%M:%S')} [ERROR] {text}\033[0m")

try:
    # 尝试相对导入
    from .tts import speak_async
except ImportError:
    try:
        # 尝试绝对导入
        from core.tts import speak_async
    except ImportError:
        # 定义简单的替代TTS函数
        def speak_async(text: str):
            pass

try:
    # 尝试相对导入
    from .ai_backend import analyze_text
    from .config import get_config, get_voice_interaction_config
except ImportError:
    try:
        # 尝试绝对导入
        from core.ai_backend import analyze_text
        from core.config import get_config, get_voice_interaction_config
    except ImportError:
        # 定义简单的替代分析函数
        def analyze_text(text, model, api_key=None):
            return f"模拟回复: {text}"


        def get_voice_interaction_config():
            return {
                'wake_word': '小爱同学',
                'wake_timeout': 10,
                'wake_threshold': 0.01,
                'energy_threshold': 300,
                'pause_threshold': 0.8,
                'auto_start': True,
                'online_recognition': True
            }

# 初始化语音识别相关变量
sr = None
pyaudio = None
VOICE_INTERACTION_AVAILABLE = False

try:
    import speech_recognition as sr
    import pyaudio

    # 为Windows系统添加CREATE_NO_WINDOW标志
    if sys.platform == 'win32':
        # 设置环境变量，防止pocketsphinx弹出CMD窗口
        os.environ["PSX_NO_CONSOLE"] = "1"
        # 尝试设置subprocess标志
        try:
            import subprocess

            subprocess_flags = subprocess.CREATE_NO_WINDOW
        except (ImportError, AttributeError):
            subprocess_flags = 0
    else:
        subprocess_flags = 0

    VOICE_INTERACTION_AVAILABLE = True
except ImportError as e:
    print(f"警告: 语音交互功能不可用 - {str(e)}")
    sr = None
    pyaudio = None
    VOICE_INTERACTION_AVAILABLE = False


class VoiceInteractionConfig:
    """语音交互配置类"""

    def __init__(self):
        # 从配置文件加载配置
        config = get_voice_interaction_config()

        # 唤醒词配置
        self.wake_word = config['wake_word']  # 唤醒词
        self.wake_timeout = config['wake_timeout']  # 唤醒后等待指令的超时时间（秒）
        self.wake_threshold = config['wake_threshold']  # 唤醒阈值

        # 语音识别配置
        self.energy_threshold = config['energy_threshold']  # 能量阈值
        self.pause_threshold = config['pause_threshold']  # 语音暂停阈值

        # 系统配置
        self.auto_start = config['auto_start']  # 是否自动启动语音交互
        self.online_recognition = config['online_recognition']  # 是否优先使用在线识别


class VoiceInteraction:
    """语音交互管理器 - 实现唤醒词检测和语音对话功能"""

    def __init__(self, config: Optional[VoiceInteractionConfig] = None):
        """
        初始化语音交互管理器
        Args:
            config: 可选的配置对象，使用默认配置如果未提供
        """
        self.config = config or VoiceInteractionConfig()
        self.recognizer = sr.Recognizer() if sr else None
        self.microphone = sr.Microphone() if sr else None
        self.is_active = False  # 是否处于激活状态（等待指令）
        self.interaction_thread = None
        self.stop_event = threading.Event()
        self.last_wake_time = 0
        self.ai_backend = None
        self.on_ai_response = None  # AI回复回调
        self.is_running = False  # 运行状态标志
        self.sphinx_available = False  # Sphinx是否可用

        # 配置语音识别
        self._configure_recognizer()
        self._check_sphinx_availability()

    def _configure_recognizer(self):
        """配置语音识别器参数"""
        if not sr or not self.recognizer:
            return

        self.recognizer.energy_threshold = self.config.energy_threshold
        self.recognizer.dynamic_energy_threshold = True
        self.recognizer.pause_threshold = self.config.pause_threshold

    def _check_sphinx_availability(self):
        """检查Sphinx是否可用"""
        if not sr or not hasattr(self.recognizer, 'recognize_sphinx'):
            self.sphinx_available = False
            return

        try:
            # 尝试使用Sphinx识别一段空白音频
            with sr.Microphone() as source:
                self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
            self.sphinx_available = True
        except Exception as e:
            self.sphinx_available = False

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

    def set_config(self, **kwargs):
        """
        动态更新配置
        Args:
            **kwargs: 配置参数
        """
        for key, value in kwargs.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)

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
            return False

        # 防止重复启动
        if self.is_running:
            return True

        # 检查麦克风是否可用
        if not sr or not self.microphone:
            console_error("语音识别模块未加载")
            return False

        try:
            with self.microphone as source:
                self.recognizer.adjust_for_ambient_noise(source, duration=1)
            console_info(f"语音交互服务已启动，唤醒词: '{self.config.wake_word}'")
        except Exception as e:
            console_error(f"麦克风初始化失败: {str(e)}")
            return False

        self.stop_event.clear()
        self.is_running = True
        self.interaction_thread = threading.Thread(target=self._interaction_loop, daemon=True)
        self.interaction_thread.start()
        return True

    def stop(self):
        """停止语音交互服务"""
        self.is_running = False
        self.stop_event.set()
        if self.interaction_thread and self.interaction_thread.is_alive():
            self.interaction_thread.join(timeout=2.0)

    def _interaction_loop(self):
        """语音交互主循环 - 持续监听唤醒词和指令"""
        # 添加初始化延迟，确保麦克风完全准备好
        time.sleep(1.0)

        while not self.stop_event.is_set():
            try:
                if not sr or not self.microphone:
                    time.sleep(1)
                    continue

                with self.microphone as source:
                    # 检查是否超时
                    current_time = time.time()
                    if self.is_active and (current_time - self.last_wake_time) > self.config.wake_timeout:
                        self.is_active = False

                    if not self.is_active:
                        # 监听唤醒词
                        try:
                            audio = self.recognizer.listen(
                                source,
                                timeout=5,
                                phrase_time_limit=3
                            )

                            # 尝试识别唤醒词
                            try:
                                # 优先使用Sphinx进行关键词检测（如果可用）
                                if self.sphinx_available:
                                    self._try_sphinx_wake_word(audio)
                            except Exception as e:
                                console_error(f"唤醒词识别异常: {str(e)}")
                                continue
                        except sr.WaitTimeoutError:
                            # 超时，继续循环
                            continue
                    else:
                        # 已唤醒，等待指令
                        try:
                            audio = self.recognizer.listen(
                                source,
                                timeout=5,
                                phrase_time_limit=10
                            )

                            # 识别语音指令
                            self._process_audio_command(audio)

                        except sr.WaitTimeoutError:
                            self.is_active = False
            except Exception as e:
                console_error(f"语音交互错误: {str(e)}")
                time.sleep(1)

    def _try_sphinx_wake_word(self, audio):
        """使用Sphinx尝试检测唤醒词"""
        try:
            # 使用Sphinx进行关键词检测
            result = self.recognizer.recognize_sphinx(
                audio,
                keyword_entries=[(self.config.wake_word, 1.0, self.config.wake_threshold)]
            )

            # Sphinx在关键词检测模式下的返回值可能有多种格式
            if result:
                # 检查唤醒词是否在结果中（处理各种可能的返回类型）
                if isinstance(result, str):
                    if self.config.wake_word in result:
                        self._handle_wake_word()
                elif isinstance(result, tuple) and len(result) > 0:
                    # 有些版本的Sphinx返回(keyword, confidence)元组
                    if result[0] == self.config.wake_word:
                        self._handle_wake_word()
                elif isinstance(result, list) and len(result) > 0:
                    # 有些情况下可能返回多个结果
                    for item in result:
                        if (isinstance(item, str) and self.config.wake_word in item) or \
                                (isinstance(item, tuple) and item[0] == self.config.wake_word):
                            self._handle_wake_word()
                            return  # 找到唤醒词后立即返回
        except sr.UnknownValueError:
            # 未识别到关键词
            pass
        except Exception as e:
            console_error(f"Sphinx唤醒词识别异常: {str(e)}")

    def _process_audio_command(self, audio):
        """处理音频命令"""
        try:
            # 优先使用Google在线识别（如果配置允许）
            if self.config.online_recognition and hasattr(self.recognizer, 'recognize_google'):
                text = self.recognizer.recognize_google(audio, language="zh-CN")
                self._process_command(text)
            else:
                raise sr.RequestError("在线识别已禁用")
        except sr.UnknownValueError:
            speak_async("抱歉，我没有听清楚")
            self.is_active = False
        except sr.RequestError:
            # Google识别失败，尝试使用Sphinx离线识别
            try:
                text = None
                if hasattr(self.recognizer, 'recognize_sphinx'):
                    text = self.recognizer.recognize_sphinx(audio, language="zh-cn")

                # 处理可能的返回值类型
                if text:
                    if isinstance(text, tuple):
                        # 只取第一个元素作为识别文本
                        text = text[0]
                    elif isinstance(text, list) and len(text) > 0:
                        # 取第一个结果
                        text = text[0] if isinstance(text[0], str) else text[0][0]

                    self._process_command(text)
                else:
                    speak_async("抱歉，我没有听清楚")
                    self.is_active = False
            except sr.UnknownValueError:
                speak_async("抱歉，我没有听清楚")
                self.is_active = False
            except Exception as e:
                console_error(f"Sphinx离线识别异常: {str(e)}")
                self.is_active = False

    def _handle_wake_word(self):
        """处理唤醒事件"""
        self.is_active = True
        self.last_wake_time = time.time()
        # 播放提示音
        speak_async("我在")

    def _process_command(self, command):
        """处理语音指令"""
        self.is_active = False  # 重置激活状态

        # 检查特殊指令
        if "退出" in command or "关闭" in command or "停止" in command:
            speak_async("好的，正在退出系统")
            # 通过回调通知主程序
            if self.on_ai_response:
                self.on_ai_response("exit")
            return

        if "切换" in command and ("模式" in command or "摄像头" in command):
            speak_async("已切换模式")
            # 通过回调通知主程序
            if self.on_ai_response:
                self.on_ai_response("switch_mode")
            return

        if "模型" in command and "切换" in command:
            speak_async("模型切换功能暂未实现")
            return

        # 将指令作为普通问题发送给AI处理
        self._process_with_ai(command)

    def _process_with_ai(self, text):
        """使用AI处理文本并返回语音回复"""
        # 如果没有设置AI后端，直接返回错误
        if not self.ai_backend:
            speak_async("AI后端未配置，请先设置AI后端")
            return

        try:
            response = None
            # 处理不同类型的AI后端
            if self.ai_backend["type"] == "qwen":
                try:
                    response = analyze_text(text, self.ai_backend["model"], self.ai_backend["api_key"])
                except Exception as e:
                    response = f"Qwen处理出错: {str(e)[:50]}"

            elif self.ai_backend["type"] == "ollama":
                try:
                    # 检查是否有纯文本模型
                    text_model = self.ai_backend["model"].replace("llava", "qwen-turbo")
                    if "llama" not in text_model and "qwen" not in text_model:
                        text_model = "qwen:1.8b-chat"
                    response = analyze_text(text, text_model)
                except Exception as e:
                    response = f"Ollama处理出错: {str(e)[:50]}"

            # 处理响应
            if response:
                # 限制回复长度
                response = response[:150]
                # 语音播报回复
                speak_async(response)

                # 触发AI回复回调
                if self.on_ai_response:
                    try:
                        self.on_ai_response(response)
                    except Exception as e:
                        console_error(f"AI回复回调执行失败: {str(e)}")
            else:
                speak_async("抱歉，没有获取到回复")

        except Exception as e:
            error_msg = f"处理过程中出错: {str(e)[:50]}"
            console_error(error_msg)
            speak_async("抱歉，处理您的请求时出错")


# 单例实例
_voice_interaction = None


def get_voice_interaction(config: Optional[VoiceInteractionConfig] = None) -> Optional[VoiceInteraction]:
    """
    获取语音交互单例实例
    Args:
        config: 可选的配置对象
    Returns:
        VoiceInteraction: 语音交互实例，如果不可用则返回None
    """
    global _voice_interaction
    if not VOICE_INTERACTION_AVAILABLE:
        return None

    if _voice_interaction is None:
        _voice_interaction = VoiceInteraction(config)
    return _voice_interaction


def is_voice_interaction_available() -> bool:
    """
    检查语音交互功能是否可用
    Returns:
        bool: 是否可用
    """
    return VOICE_INTERACTION_AVAILABLE