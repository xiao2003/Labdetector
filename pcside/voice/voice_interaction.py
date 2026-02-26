#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pcside/voice/voice_interaction.py - 独立语音交互中枢 (暴力寻麦修复版 + 纯净输出与精准RAG)
"""
import threading
import time
import os
import sys
import json
from typing import Optional

current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))

from pcside.core.logger import console_info, console_error
from pcside.core.config import get_config
from pcside.core.ai_backend import ask_assistant_with_rag
from pcside.knowledge_base.rag_engine import rag_engine

try:
    from pcside.core.tts import speak_async

    try:
        from pcside.core.tts import stop_tts
    except ImportError:
        def stop_tts():
            pass
except ImportError:
    def speak_async(t):
        pass

    def stop_tts():
        pass

try:
    import vosk

    vosk.SetLogLevel(-1)
    VOSK_AVAILABLE = True
except ImportError:
    VOSK_AVAILABLE = False
    console_error("未安装 Vosk，建议运行: pip install vosk 以获得纯离线语音能力")

try:
    import speech_recognition as sr
    import pyaudio

    if sys.platform == 'win32':
        os.environ["PSX_NO_CONSOLE"] = "1"
    VOICE_INTERACTION_AVAILABLE = True
except ImportError as e:
    console_error(f"语音交互功能不可用: {e}")
    sr = None
    pyaudio = None
    VOICE_INTERACTION_AVAILABLE = False


class VoiceInteractionConfig:
    def __init__(self):
        self.wake_word = str(get_config('voice_interaction.wake_word', '小爱同学'))
        self.wake_timeout = float(get_config('voice_interaction.wake_timeout', 10.0))
        self.wake_threshold = float(get_config('voice_interaction.wake_threshold', 0.01))
        self.energy_threshold = int(get_config('voice_interaction.energy_threshold', 300))
        self.pause_threshold = float(get_config('voice_interaction.pause_threshold', 0.8))

        online_rec = get_config('voice_interaction.online_recognition', True)
        self.online_recognition = str(online_rec).lower() == 'true'

        current_dir = os.path.dirname(os.path.abspath(__file__))
        default_model_dir = os.path.join(current_dir, 'model')
        self.vosk_model_path = str(get_config('voice_interaction.vosk_model_path', default_model_dir))


class VoiceInteraction:
    def __init__(self, config: Optional[VoiceInteractionConfig] = None):
        self.config = config or VoiceInteractionConfig()
        self.recognizer = sr.Recognizer() if sr else None
        self.microphone = None
        self.is_active = False
        self.interaction_thread = None
        self.stop_event = threading.Event()
        self.last_wake_time = 0
        self.ai_backend = None
        self.is_running = False
        self.get_latest_frame_callback = None

        self.vosk_model = None
        self.vosk_recognizer = None
        self.sphinx_available = False

        self._configure_recognizer()
        self._init_offline_engine()

    def _configure_recognizer(self):
        if self.recognizer:
            self.recognizer.energy_threshold = self.config.energy_threshold
            self.recognizer.dynamic_energy_threshold = True
            self.recognizer.pause_threshold = self.config.pause_threshold
            self.sphinx_available = hasattr(self.recognizer, 'recognize_sphinx')

    def _init_offline_engine(self):
        if VOSK_AVAILABLE:
            if os.path.exists(self.config.vosk_model_path):
                try:
                    console_info(f"正在加载 Vosk 离线语音模型...")
                    self.vosk_model = vosk.Model(self.config.vosk_model_path)
                    self.vosk_recognizer = vosk.KaldiRecognizer(self.vosk_model, 16000)
                    console_info("离线语音听写模块加载成功！(支持完全断网)")
                except Exception as e:
                    console_error(f"Vosk模型加载失败: {e}")

    def set_ai_backend(self, backend: str, model: str = "", api_key: Optional[str] = None):
        self.ai_backend = {"type": backend, "model": model, "api_key": api_key}

    def _recognize_audio_data(self, audio_data) -> str:
        if self.vosk_recognizer:
            try:
                raw_pcm = audio_data.get_raw_data(convert_rate=16000, convert_width=2)
                self.vosk_recognizer.AcceptWaveform(raw_pcm)
                res = json.loads(self.vosk_recognizer.FinalResult())
                text = res.get("text", "").replace(" ", "")
                if text: return text
            except Exception:
                pass

        if self.config.online_recognition and hasattr(self.recognizer, 'recognize_google'):
            try:
                return self.recognizer.recognize_google(audio_data, language="zh-CN")
            except Exception:
                pass

        return ""

    def _get_working_microphone(self):
        if not sr: return None
        try:
            mic = sr.Microphone()
            with mic as source:
                pass
            return mic
        except Exception as e:
            console_error(f"默认录音通道被系统锁定 ({e})，正在扫描备用线路...")

        for idx, name in enumerate(sr.Microphone.list_microphone_names()):
            if any(x in name for x in ["Output", "扬声器", "Speakers", "映射器"]):
                continue
            try:
                mic = sr.Microphone(device_index=idx)
                with mic as source:
                    pass
                console_info(f"成功接管备用录音线路: [{idx}] {name}")
                return mic
            except:
                continue
        return None

    def start(self) -> bool:
        if not VOICE_INTERACTION_AVAILABLE or self.is_running: return False

        self.microphone = self._get_working_microphone()
        if not self.microphone:
            console_error("[VOICE]遍历了系统中所有音频设备，均无法访问麦克风！(请检查Windows独占模式设置)")
            return False

        try:
            console_info("[VOICE]正在接通麦克风并校准底噪...")
            with self.microphone as source:
                self.recognizer.adjust_for_ambient_noise(source, duration=1)
            console_info(f"[VOICE]智能语音中枢已完全启动，唤醒词: '{self.config.wake_word}'")
        except Exception as e:
            console_error(f"[VOICE]启动麦克风时发生严重冲突: {e}")
            return False

        self.stop_event.clear()
        self.is_running = True
        self.interaction_thread = threading.Thread(target=self._interaction_loop, daemon=True)
        self.interaction_thread.start()
        return True

    def stop(self):
        self.is_running = False
        self.stop_event.set()

    def _interaction_loop(self):
        time.sleep(1.0)
        while not self.stop_event.is_set():
            try:
                if not self.microphone: time.sleep(1); continue
                with self.microphone as source:
                    if self.is_active and (time.time() - self.last_wake_time) > self.config.wake_timeout:
                        self.is_active = False
                        console_info("[VOICE]唤醒超时，重新进入待机模式。")

                    if not self.is_active:
                        try:
                            audio = self.recognizer.listen(source, timeout=1, phrase_time_limit=3)
                            text = self._recognize_audio_data(audio)
                            if self.config.wake_word in text:
                                self._handle_wake_word()
                        except sr.WaitTimeoutError:
                            pass
                        except Exception:
                            pass
                    else:
                        try:
                            console_info("[VOICE]正在聆听指令...")
                            audio = self.recognizer.listen(source, timeout=5, phrase_time_limit=10)
                            text = self._recognize_audio_data(audio)

                            if text:
                                self._route_command(text)
                            else:
                                self.is_active = False
                                console_info("[VOICE]没听清指令，进入待机。")
                        except sr.WaitTimeoutError:
                            self.is_active = False
                            console_info("[VOICE]没听到指令，进入待机。")
            except Exception:
                time.sleep(1)

    def _handle_wake_word(self):
        stop_tts()
        self.is_active = True
        self.last_wake_time = time.time()
        console_info(f"[VOICE]检测到唤醒词！")
        speak_async("[VOICE]我在。")

    def _route_command(self, command: str):
        console_info(f"[VOICE]收到语音输入: {command}")

        if "退出" in command or "关闭" in command:
            speak_async("[VOICE]好的，停止语音服务。")
            self.is_active = False
            return

        if "记一下" in command or "记录" in command:
            stop_tts()
            note_content = command.split("记一下")[-1].split("记录")[-1].strip(" ，。！、\n")

            if "我说完了" in note_content:
                final_note = note_content.replace("我说完了", "").strip(" ，。！、")
                if final_note:
                    rag_engine.save_and_ingest_note(f"[长期记忆]{time.strftime('%Y-%m-%d %H:%M:%S')}：{final_note}")
                speak_async("[VOICE]我记下了，您还有别的需要吗？")
                self.is_active = True
                self.last_wake_time = time.time()
                return
            else:
                self._record_long_note(initial_text=note_content)
                return

        self.is_active = False
        if not self.ai_backend: return

        context = rag_engine.retrieve_context(command)
        current_frame = self.get_latest_frame_callback() if self.get_latest_frame_callback else None

        answer = ask_assistant_with_rag(
            frame=current_frame,
            question=command,
            rag_context=context,
            model_name=self.ai_backend.get("model", "qwen-vl-max")
        )
        console_info(f"AI回答: {answer}")
        speak_async(answer)

    def _record_long_note(self, initial_text: str = ""):
        speak_async("正在为您记录，结束请说，我说完了。")
        accumulated = initial_text + "，" if initial_text else ""
        timeout_retries = 0

        while not self.stop_event.is_set():
            try:
                with self.microphone as source:
                    console_info("[记录中] 正在倾听... (说'我说完了'结束)")
                    audio = self.recognizer.listen(source, timeout=5, phrase_time_limit=15)
                    text = self._recognize_audio_data(audio)

                    if text:
                        console_info(f"听写片段: {text}")
                        timeout_retries = 0
                        if "我说完了" in text:
                            final_part = text.replace("我说完了", "").strip(" ，。！、")
                            if final_part: accumulated += final_part + "。"
                            break
                        else:
                            accumulated += text + "，"
            except sr.WaitTimeoutError:
                timeout_retries += 1
                if timeout_retries >= 3:
                    speak_async("录音等待超时，已为您自动结束。")
                    break
                continue
            except Exception:
                continue

        if accumulated.strip("，。 "):
            rag_engine.save_and_ingest_note(
                f"【长期语音记忆】{time.strftime('%Y-%m-%d %H:%M:%S')}：{accumulated.strip('，。 ')}")
            console_info(f"长语音已完整归档入库！")

        speak_async("我记下了，您还有别的需要吗？")
        self.is_active = True
        self.last_wake_time = time.time()


_voice_interaction = None


def get_voice_interaction() -> Optional[VoiceInteraction]:
    global _voice_interaction
    if not VOICE_INTERACTION_AVAILABLE: return None
    if _voice_interaction is None:
        _voice_interaction = VoiceInteraction()
    return _voice_interaction