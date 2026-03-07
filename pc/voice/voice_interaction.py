#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Voice interaction controller for local PC and remote Pi sessions."""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from typing import Any, Callable, Optional

from pc.core.ai_backend import ask_assistant_with_rag
from pc.core.config import get_config
from pc.core.logger import console_error, console_info
from pc.core.voice_round_archive import get_voice_round_archive
from pc.knowledge_base.rag_engine import knowledge_manager

try:
    from pc.core.tts import speak_async
    try:
        from pc.core.tts import stop_tts
    except ImportError:
        def stop_tts() -> None:
            return
except ImportError:
    def speak_async(_text: str) -> None:
        return

    def stop_tts() -> None:
        return

try:
    import vosk

    vosk.SetLogLevel(-1)
    VOSK_AVAILABLE = True
except ImportError:
    VOSK_AVAILABLE = False
    console_error("未安装 Vosk，建议执行 pip install vosk 以获得离线语音能力")

try:
    import speech_recognition as sr
    import pyaudio  # noqa: F401

    if sys.platform == "win32":
        os.environ["PSX_NO_CONSOLE"] = "1"
    VOICE_INTERACTION_AVAILABLE = True
except ImportError as exc:
    console_error(f"语音交互功能不可用: {exc}")
    sr = None
    VOICE_INTERACTION_AVAILABLE = False


def _common_memory_engine():
    return knowledge_manager.get_scope("common")


def _build_voice_rag_context(command: str) -> str:
    try:
        bundle = knowledge_manager.build_scope_bundle(command, "expert.lab_qa_expert", top_k=3)
    except Exception as exc:
        console_error(f"语音知识库检索失败: {exc}")
        return ""

    parts = []
    context = str(bundle.get("context") or "").strip()
    if context:
        parts.append(context)

    rows = bundle.get("structured_rows") or []
    if rows:
        detail_lines = []
        for row in rows[:3]:
            scope_name = row.get("scope_title", row.get("scope", "知识库"))
            detail_lines.append(f"[{scope_name}] {row.get('name', '')}: {str(row.get('value', ''))[:120]}")
        parts.append("结构化知识\n" + "\n".join(detail_lines))

    return "\n\n".join(part for part in parts if part.strip())


class VoiceInteractionConfig:
    def __init__(self) -> None:
        self.wake_word = str(get_config("voice_interaction.wake_word", "小爱同学"))
        self.wake_timeout = float(get_config("voice_interaction.wake_timeout", 10.0))
        self.energy_threshold = int(get_config("voice_interaction.energy_threshold", 300))
        self.pause_threshold = float(get_config("voice_interaction.pause_threshold", 0.8))
        self.online_recognition = str(get_config("voice_interaction.online_recognition", True)).lower() == "true"
        self.vosk_model_path = str(
            get_config(
                "voice_interaction.vosk_model_path",
                os.path.join(os.path.dirname(__file__), "model"),
            )
        )


class VoiceInteraction:
    def __init__(self, config: Optional[VoiceInteractionConfig] = None) -> None:
        self.config = config or VoiceInteractionConfig()
        self.recognizer = sr.Recognizer() if sr else None
        self.microphone = None
        self.is_active = False
        self.is_running = False
        self.interaction_thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
        self.last_wake_time = 0.0
        self.ai_backend: Dict[str, Any] = {"type": "ollama", "model": "", "api_key": ""}
        self.get_latest_frame_callback: Optional[Callable[[], Any]] = None
        self.vosk_model = None
        self.vosk_recognizer = None
        self.round_archive = get_voice_round_archive()
        self.session_meta: Dict[str, Any] = {}

        self._configure_recognizer()
        self._init_offline_engine()

    def _configure_recognizer(self) -> None:
        if not self.recognizer:
            return
        self.recognizer.energy_threshold = self.config.energy_threshold
        self.recognizer.dynamic_energy_threshold = True
        self.recognizer.pause_threshold = self.config.pause_threshold

    def _init_offline_engine(self) -> None:
        if not VOSK_AVAILABLE:
            return
        if not os.path.exists(self.config.vosk_model_path):
            return
        try:
            console_info("正在加载 Vosk 离线语音模型...")
            self.vosk_model = vosk.Model(self.config.vosk_model_path)
            self.vosk_recognizer = vosk.KaldiRecognizer(self.vosk_model, 16000)
            console_info("离线语音模块已就绪")
        except Exception as exc:
            console_error(f"Vosk 模型加载失败: {exc}")

    def set_ai_backend(self, backend: str, model: str = "", api_key: Optional[str] = None) -> None:
        self.ai_backend = {"type": backend, "model": model, "api_key": api_key or ""}

    def open_runtime_session(self, mode: str, source: str, metadata: Optional[dict[str, Any]] = None) -> str:
        meta = {
            "mode": mode,
            "source": source,
            "backend": self.ai_backend.get("type", ""),
            "model": self.ai_backend.get("model", ""),
        }
        if metadata:
            meta.update(metadata)
        self.session_meta = meta
        return self.round_archive.open_session(mode=mode, source=source, metadata=meta)

    def close_runtime_session(self) -> None:
        self.round_archive.close_session()
        self.session_meta = {}

    def _recognize_audio_data(self, audio_data: Any) -> str:
        if self.vosk_recognizer:
            try:
                raw_pcm = audio_data.get_raw_data(convert_rate=16000, convert_width=2)
                self.vosk_recognizer.AcceptWaveform(raw_pcm)
                result = json.loads(self.vosk_recognizer.FinalResult())
                text = str(result.get("text", "")).replace(" ", "")
                if text:
                    return text
            except Exception:
                pass

        if self.config.online_recognition and self.recognizer and hasattr(self.recognizer, "recognize_google"):
            try:
                return self.recognizer.recognize_google(audio_data, language="zh-CN")
            except Exception:
                pass
        return ""

    def _get_working_microphone(self) -> Any | None:
        if not sr:
            return None
        try:
            mic = sr.Microphone()
            with mic as source:
                pass
            return mic
        except Exception as exc:
            console_error(f"默认麦克风不可用，正在扫描其它输入设备: {exc}")

        for idx, name in enumerate(sr.Microphone.list_microphone_names()):
            lowered = str(name).lower()
            if any(marker in lowered for marker in ("output", "speaker", "扬声器", "映射器")):
                continue
            try:
                mic = sr.Microphone(device_index=idx)
                with mic as source:
                    pass
                console_info(f"已切换到备用麦克风: [{idx}] {name}")
                return mic
            except Exception:
                continue
        return None

    def start(self) -> bool:
        if not VOICE_INTERACTION_AVAILABLE or self.is_running:
            return False

        self.microphone = self._get_working_microphone()
        if not self.microphone:
            console_error("[VOICE] 未检测到可用麦克风，语音助手无法启动")
            return False

        try:
            print("")
            console_info("[VOICE] 正在接入麦克风并校准环境噪声...")
            with self.microphone as source:
                assert self.recognizer is not None
                self.recognizer.adjust_for_ambient_noise(source, duration=1)
            console_info(f"[VOICE] 语音助手已启动，唤醒词: {self.config.wake_word}")
            console_info("[VOICE] 状态：等待唤醒")
        except Exception as exc:
            console_error(f"[VOICE] 麦克风初始化失败: {exc}")
            return False

        self.stop_event.clear()
        self.is_running = True
        self.interaction_thread = threading.Thread(target=self._interaction_loop, daemon=True, name="VoiceInteraction")
        self.interaction_thread.start()
        return True

    def stop(self) -> None:
        self.is_running = False
        self.is_active = False
        self.stop_event.set()

    def _interaction_loop(self) -> None:
        time.sleep(0.8)
        while not self.stop_event.is_set():
            try:
                if not self.microphone or not self.recognizer:
                    time.sleep(1.0)
                    continue
                with self.microphone as source:
                    if self.is_active and (time.time() - self.last_wake_time) > self.config.wake_timeout:
                        self.is_active = False
                        console_info("[VOICE] 唤醒超时，回到待机状态")

                    if not self.is_active:
                        try:
                            audio = self.recognizer.listen(source, timeout=1, phrase_time_limit=3)
                            text = self._recognize_audio_data(audio)
                            if self.config.wake_word and self.config.wake_word in text:
                                self._handle_wake_word()
                        except sr.WaitTimeoutError:
                            pass
                        except Exception:
                            pass
                    else:
                        try:
                            console_info("[VOICE] 正在监听指令...")
                            audio = self.recognizer.listen(source, timeout=5, phrase_time_limit=10)
                            text = self._recognize_audio_data(audio)
                            if text:
                                self._route_command(text)
                            else:
                                self.is_active = False
                                console_info("[VOICE] 未识别到有效指令，回到待机状态")
                        except sr.WaitTimeoutError:
                            self.is_active = False
                            console_info("[VOICE] 指令等待超时，回到待机状态")
            except Exception:
                time.sleep(1.0)

    def _handle_wake_word(self) -> None:
        stop_tts()
        self.is_active = True
        self.last_wake_time = time.time()
        console_info("[VOICE] 已检测到唤醒词")
        speak_async("我在。")

    def _deliver_response(
        self,
        response: str,
        *,
        speak_response: bool,
        reply_callback: Optional[Callable[[str], None]],
    ) -> None:
        if reply_callback is not None:
            reply_callback(response)
        elif speak_response and response:
            speak_async(response)

    def _record_round(self, command: str, response: str, source: str, metadata: Optional[dict[str, Any]] = None) -> None:
        payload = dict(self.session_meta)
        if metadata:
            payload.update(metadata)
        self.round_archive.record_round(prompt=command, response=response, source=source, metadata=payload)

    @staticmethod
    def _extract_note_content(command: str) -> str:
        content = command
        for prefix in ("记一下", "记录一下", "记录", "帮我记录", "请记录"):
            if prefix in content:
                content = content.split(prefix, 1)[-1]
                break
        return content.strip(" ，。！？\n")

    def _save_note(self, note_content: str) -> bool:
        if not note_content.strip():
            return False
        text = f"[语音记录]{time.strftime('%Y-%m-%d %H:%M:%S')}：{note_content.strip()}"
        return _common_memory_engine().save_and_ingest_note(text)

    def process_text_command(
        self,
        command: str,
        *,
        source: str = "pc_local",
        speak_response: bool = True,
        reply_callback: Optional[Callable[[str], None]] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> str:
        text = str(command or "").strip()
        if not text:
            return ""
        console_info(f"[VOICE] 收到语音输入({source}): {text}")

        round_meta = dict(metadata or {})
        round_meta.setdefault("mode", self.session_meta.get("mode", "adhoc"))
        round_meta.setdefault("backend", self.ai_backend.get("type", ""))
        round_meta.setdefault("model", self.ai_backend.get("model", ""))

        local_origin = source.startswith("pc")

        try:
            if any(keyword in text for keyword in ("退出", "关闭语音", "结束语音")):
                response = "好的，语音助手已结束本轮待命。"
                self._deliver_response(response, speak_response=speak_response, reply_callback=reply_callback)
                self._record_round(text, response, source, round_meta)
                if local_origin:
                    self.is_active = False
                return response

            if any(keyword in text for keyword in ("记一下", "记录", "帮我记录")):
                note_content = self._extract_note_content(text)
                if note_content:
                    saved = self._save_note(note_content)
                    response = "已写入公共背景知识库。" if saved else "记录失败，请稍后重试。"
                    self._deliver_response(response, speak_response=speak_response, reply_callback=reply_callback)
                    self._record_round(text, response, source, {**round_meta, "note_saved": saved})
                    if local_origin:
                        self.is_active = True
                        self.last_wake_time = time.time()
                    return response

            current_frame = self.get_latest_frame_callback() if self.get_latest_frame_callback else None
            context = _build_voice_rag_context(text)
            answer = ask_assistant_with_rag(
                frame=current_frame,
                question=text,
                rag_context=context,
                model_name=self.ai_backend.get("model", "qwen-vl-max"),
            )
            console_info(f"[VOICE] AI 回答: {answer}")
            self._deliver_response(answer, speak_response=speak_response, reply_callback=reply_callback)
            self._record_round(
                text,
                answer,
                source,
                {
                    **round_meta,
                    "has_frame": bool(current_frame is not None),
                    "rag_enabled": bool(context.strip()),
                },
            )
            return answer
        except Exception as exc:
            error_text = f"语音指令处理失败: {exc}"
            console_error(error_text)
            self._deliver_response(error_text, speak_response=False, reply_callback=reply_callback)
            self._record_round(text, error_text, source, {**round_meta, "error": True})
            return error_text
        finally:
            if local_origin:
                self.is_active = False

    def process_remote_command(
        self,
        node_id: str,
        command: str,
        reply_callback: Optional[Callable[[str], None]] = None,
    ) -> str:
        return self.process_text_command(
            command,
            source=f"pi:{node_id}",
            speak_response=False,
            reply_callback=reply_callback,
            metadata={"node_id": node_id},
        )

    def _route_command(self, command: str) -> str:
        return self.process_text_command(command, source="pc_local", speak_response=True)


_voice_interaction: Optional[VoiceInteraction] = None


def get_voice_interaction() -> Optional[VoiceInteraction]:
    global _voice_interaction
    if not VOICE_INTERACTION_AVAILABLE:
        return None
    if _voice_interaction is None:
        _voice_interaction = VoiceInteraction()
    return _voice_interaction
