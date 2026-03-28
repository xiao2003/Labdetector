#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Voice interaction controller for local PC and remote Pi sessions."""

from __future__ import annotations

import json
import io
import os
import re
import sys
import threading
import time
import warnings
from contextlib import redirect_stderr, redirect_stdout
from typing import Any, Callable, Optional

import numpy as np

from pc.app_identity import resource_path
from pc.core.ai_backend import ask_assistant_with_rag
from pc.core.config import get_config
from pc.core.logger import console_error, console_info
from pc.core.orchestrator import orchestrator
from pc.core.runtime_assets import sensevoice_model_dir, vosk_model_dir
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
    import speech_recognition as sr
    import pyaudio  # noqa: F401

    if sys.platform == "win32":
        os.environ["PSX_NO_CONSOLE"] = "1"
    VOICE_INTERACTION_AVAILABLE = True
except ImportError as exc:
    console_error(f"语音交互功能不可用: {exc}")
    sr = None
    VOICE_INTERACTION_AVAILABLE = False

try:
    import vosk

    vosk.SetLogLevel(-1)
    VOSK_AVAILABLE = True
except ImportError:
    vosk = None
    VOSK_AVAILABLE = False

FUNASR_IMPORT_ERROR = ""
try:
    _funasr_import_buffer = io.StringIO()
    with redirect_stdout(_funasr_import_buffer), redirect_stderr(_funasr_import_buffer):
        from funasr import AutoModel as FunASRAutoModel
except ImportError as exc:
    FunASRAutoModel = None
    FUNASR_IMPORT_ERROR = str(exc)
    console_error(f"[VOICE] FunASR 导入失败: {exc}")

FUNASR_POSTPROCESS_IMPORT_ERROR = ""
try:
    from funasr.utils.postprocess_utils import rich_transcription_postprocess
except ImportError as exc:
    rich_transcription_postprocess = None
    FUNASR_POSTPROCESS_IMPORT_ERROR = str(exc)

OPENWAKEWORD_IMPORT_ERROR = ""
try:
    from openwakeword.model import Model as OpenWakeWordModel
except ImportError as exc:
    OpenWakeWordModel = None
    OPENWAKEWORD_IMPORT_ERROR = str(exc)
    console_error(f"[VOICE] openWakeWord 导入失败: {exc}")


def _common_memory_engine():
    return knowledge_manager.get_scope("common")


def _build_voice_rag_context(command: str) -> str:
    try:
        bundle = knowledge_manager.build_scope_bundle(command, "expert.lab_qa_expert", top_k=3)
    except Exception as exc:
        console_error(f"语音知识库检索失败: {exc}")
        return ""

    parts: list[str] = []
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
        wake_aliases_raw = str(
            get_config(
                "voice_interaction.wake_aliases",
                "小爱同学,小爱同,小爱,小艾同学,晓爱同学,哎同学,爱同学",
            )
        )
        self.wake_aliases = [item.strip() for item in wake_aliases_raw.split(",") if item.strip()]
        self.wake_timeout = float(get_config("voice_interaction.wake_timeout", 10.0))
        self.energy_threshold = int(get_config("voice_interaction.energy_threshold", 300))
        self.pause_threshold = float(get_config("voice_interaction.pause_threshold", 1.0))
        self.wake_phrase_time_limit = float(get_config("voice_interaction.wake_phrase_time_limit", 4.0))
        self.command_timeout = float(get_config("voice_interaction.command_timeout", 6.0))
        self.command_phrase_time_limit = float(get_config("voice_interaction.command_phrase_time_limit", 12.0))
        self.online_recognition = str(get_config("voice_interaction.online_recognition", True)).lower() == "true"
        self.vosk_model_path = str(get_config("voice_interaction.vosk_model_path", str(vosk_model_dir())))

        self.asr_engine = str(get_config("voice_interaction.asr_engine", "auto")).lower()
        self.wake_engine = str(get_config("voice_interaction.wake_engine", "auto")).lower()
        self.funasr_model = str(get_config("voice_interaction.funasr_model", str(sensevoice_model_dir())))
        self.funasr_model_repo_id = str(get_config("voice_interaction.funasr_model_repo_id", "iic/SenseVoiceSmall"))
        self.funasr_vad_model = str(get_config("voice_interaction.funasr_vad_model", "fsmn-vad"))
        self.funasr_punc_model = str(get_config("voice_interaction.funasr_punc_model", "ct-punc-c"))
        self.funasr_device = str(get_config("voice_interaction.funasr_device", "auto"))
        self.funasr_language = str(get_config("voice_interaction.funasr_language", "zh"))
        self.funasr_use_itn = str(get_config("voice_interaction.funasr_use_itn", False)).lower() == "true"

        self.openwakeword_model_path = str(get_config("voice_interaction.openwakeword_model_path", "")).strip()
        self.openwakeword_threshold = float(get_config("voice_interaction.openwakeword_threshold", 0.45))
        self.openwakeword_chunk_size = int(get_config("voice_interaction.openwakeword_chunk_size", 1280))


def _existing_model_dir(*relative_candidates: str) -> str:
    for candidate in relative_candidates:
        path = resource_path(candidate)
        if path.exists():
            return str(path)
        return str(resource_path(relative_candidates[0]))


class VoiceInteraction:
    def __init__(
        self,
        config: Optional[VoiceInteractionConfig] = None,
        *,
        initialize_audio_models: bool = True,
    ) -> None:
        self.config = config or VoiceInteractionConfig()
        self.initialize_audio_models = bool(initialize_audio_models)
        self.recognizer = sr.Recognizer() if sr else None
        self.microphone = None
        self.is_active = False
        self.is_running = False
        self.interaction_thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
        self.last_wake_time = 0.0
        self.ai_backend: dict[str, Any] = {"type": "ollama", "model": "", "api_key": ""}
        self.get_latest_frame_callback: Optional[Callable[[], Any]] = None
        self.round_archive = get_voice_round_archive()
        self.session_meta: dict[str, Any] = {}
        self.session_rounds: list[dict[str, Any]] = []
        self.pending_note_items: list[str] = []
        self.local_command_handler: Optional[Callable[[str, str], Optional[str]]] = None
        self.session_state = "idle"
        self._speak_state_timer: Optional[threading.Timer] = None

        self.vosk_model = None
        self.vosk_recognizer = None
        self.funasr_model = None
        self.funasr_runtime_device = "cpu"
        self.openwakeword_model = None

        self._configure_recognizer()
        if self.initialize_audio_models:
            self._init_voice_models()

    def _configure_recognizer(self) -> None:
        if not self.recognizer:
            return
        self.recognizer.energy_threshold = self.config.energy_threshold
        self.recognizer.dynamic_energy_threshold = True
        self.recognizer.pause_threshold = self.config.pause_threshold
        self.recognizer.non_speaking_duration = 0.5
        self.recognizer.phrase_threshold = 0.25

    def _init_voice_models(self) -> None:
        self._init_funasr_engine()
        self._init_vosk_engine()
        self._init_openwakeword_engine()

    def _init_funasr_engine(self) -> None:
        if FunASRAutoModel is None:
            if FUNASR_IMPORT_ERROR:
                console_error(f"[VOICE] FunASR 不可用，已回退到其他识别链路: {FUNASR_IMPORT_ERROR}")
            return
        if self.config.asr_engine not in ("auto", "funasr"):
            return
        try:
            model_source = self._resolve_funasr_model_source()
            resolved_device = self._resolve_funasr_device()
            kwargs: dict[str, Any] = {
                "model": model_source,
                "device": resolved_device,
                "disable_update": True,
                "trust_remote_code": False,
            }
            if self.config.funasr_vad_model and os.path.exists(self.config.funasr_vad_model):
                kwargs["vad_model"] = self.config.funasr_vad_model
            if self.config.funasr_punc_model and os.path.exists(self.config.funasr_punc_model):
                kwargs["punc_model"] = self.config.funasr_punc_model
            self.funasr_runtime_device = resolved_device
            console_info(f"[VOICE] 正在加载 FunASR 模型: {model_source} | device={resolved_device}")
            self.funasr_model = self._build_funasr_model(kwargs)
            console_info("[VOICE] FunASR 语音识别已就绪")
        except Exception as exc:
            console_error(f"[VOICE] FunASR 初始化失败，将回退到其他识别链路: {exc}")
            self.funasr_model = None
            self.funasr_runtime_device = "cpu"

    def _resolve_funasr_model_source(self) -> str:
        configured = str(self.config.funasr_model or "").strip()
        local_candidates = [
            configured,
            str(sensevoice_model_dir()),
        ]
        for candidate in local_candidates:
            if not candidate:
                continue
            config_file = os.path.join(candidate, "configuration.json")
            if os.path.exists(config_file):
                return candidate
        if self.config.asr_engine == "funasr":
            return self.config.funasr_model_repo_id or configured
        raise FileNotFoundError("未检测到本地 SenseVoice 模型，自动模式将回退到其他识别链路。")

    def _build_funasr_model(self, kwargs: dict[str, Any]) -> Any:
        # Suppress third-party startup chatter so the runtime log keeps only our own status lines.
        os.environ.setdefault("MODELSCOPE_LOG_LEVEL", "40")
        os.environ.setdefault("FUNASR_DISABLE_REMOTE_CODE_WARNING", "1")
        buffer = io.StringIO()
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message=".*pin_memory.*")
            warnings.filterwarnings("ignore", message=".*trust_remote_code.*")
            with redirect_stdout(buffer), redirect_stderr(buffer):
                model = FunASRAutoModel(**kwargs)
        return model

    def _resolve_funasr_device(self) -> str:
        configured = (self.config.funasr_device or "auto").strip().lower()
        if configured not in ("", "auto"):
            return configured
        try:
            import torch

            if torch.cuda.is_available():
                console_info("[VOICE] 检测到可用 CUDA，FunASR 将使用 GPU。")
                return "cuda"
        except Exception as exc:
            console_error(f"[VOICE] 检测 CUDA 失败，将回退到 CPU: {exc}")
        console_info("[VOICE] 未检测到可用 CUDA，FunASR 将使用 CPU。")
        return "cpu"

    def _init_vosk_engine(self) -> None:
        if not VOSK_AVAILABLE:
            return
        if not os.path.exists(self.config.vosk_model_path):
            return
        try:
            console_info("[VOICE] 正在加载 Vosk 离线语音模型...")
            self.vosk_model = vosk.Model(self.config.vosk_model_path)
            self.vosk_recognizer = vosk.KaldiRecognizer(self.vosk_model, 16000)
            console_info("[VOICE] Vosk 离线语音模块已就绪")
        except Exception as exc:
            console_error(f"[VOICE] Vosk 模型加载失败: {exc}")
            self.vosk_model = None
            self.vosk_recognizer = None

    def _init_openwakeword_engine(self) -> None:
        if OpenWakeWordModel is None:
            if OPENWAKEWORD_IMPORT_ERROR:
                console_error(f"[VOICE] openWakeWord 不可用，已回退到文本唤醒匹配: {OPENWAKEWORD_IMPORT_ERROR}")
            return
        if self.config.wake_engine not in ("auto", "openwakeword"):
            return
        if not self.config.openwakeword_model_path:
            console_info("[VOICE] 未配置 openWakeWord 自定义唤醒模型，继续使用文本唤醒匹配")
            return
        if not os.path.exists(self.config.openwakeword_model_path):
            console_error(f"[VOICE] openWakeWord 模型不存在: {self.config.openwakeword_model_path}")
            return
        try:
            console_info(f"[VOICE] 正在加载 openWakeWord 模型: {self.config.openwakeword_model_path}")
            self.openwakeword_model = OpenWakeWordModel(wakeword_models=[self.config.openwakeword_model_path])
            console_info("[VOICE] openWakeWord 唤醒检测已就绪")
        except Exception as exc:
            console_error(f"[VOICE] openWakeWord 初始化失败，将回退到文本唤醒匹配: {exc}")
            self.openwakeword_model = None

    def set_ai_backend(self, backend: str, model: str = "", api_key: Optional[str] = None) -> None:
        self.ai_backend = {"type": backend, "model": model, "api_key": api_key or ""}

    def set_local_command_handler(self, handler: Optional[Callable[[str, str], Optional[str]]]) -> None:
        self.local_command_handler = handler

    def open_runtime_session(self, mode: str, source: str, metadata: Optional[dict[str, Any]] = None) -> str:
        meta = {
            "mode": mode,
            "source": source,
            "backend": self.ai_backend.get("type", ""),
            "model": self.ai_backend.get("model", ""),
            "asr_engine": self._active_asr_engine_name(),
            "wake_engine": self._active_wake_engine_name(),
        }
        if metadata:
            meta.update(metadata)
        self.session_meta = meta
        self.session_rounds = []
        self.pending_note_items = []
        return self.round_archive.open_session(mode=mode, source=source, metadata=meta)

    def close_runtime_session(self) -> None:
        self._finalize_session_summary()
        self.round_archive.close_session()
        self.session_meta = {}
        self.session_rounds = []
        self.pending_note_items = []

    def _active_asr_engine_name(self) -> str:
        if self.funasr_model is not None:
            return "funasr"
        if self.vosk_recognizer is not None:
            return "vosk"
        if self.config.online_recognition:
            return "google"
        return "none"

    def _active_wake_engine_name(self) -> str:
        if self.openwakeword_model is not None:
            return "openwakeword+text"
        return "text"

    @staticmethod
    def _normalize_text(text: str) -> str:
        normalized = re.sub(r"\s+", "", str(text or ""))
        normalized = re.sub(r"[，。！？、,.!?\-—_:;\"'`~·]+", "", normalized)
        return normalized.lower()

    def _wake_matches(self, text: str) -> bool:
        normalized = self._normalize_text(text)
        if not normalized:
            return False

        aliases = list(self.config.wake_aliases)
        if self.config.wake_word:
            aliases.insert(0, self.config.wake_word)

        for alias in aliases:
            alias_norm = self._normalize_text(alias)
            if alias_norm and alias_norm in normalized:
                return True

        if "同学" in normalized and any(marker in normalized for marker in ("小爱", "小艾", "晓爱", "爱同", "哎同")):
            return True
        return False

    def _is_stop_playback_command(self, text: str) -> bool:
        normalized = self._normalize_text(text)
        return any(keyword in normalized for keyword in ("停止播报", "停止说话", "别说了", "闭嘴"))

    def _stop_playback(self) -> None:
        stop_tts()
        self.is_active = False
        console_info("[VOICE] 已停止语音播报")

    def _recognize_with_funasr(self, audio_data: Any) -> str:
        if self.funasr_model is None:
            return ""

        try:
            raw_pcm = audio_data.get_raw_data(convert_rate=16000, convert_width=2)
            pcm = np.frombuffer(raw_pcm, dtype=np.int16)
            if pcm.size == 0:
                return ""
            waveform = pcm.astype(np.float32) / 32768.0
            buffer = io.StringIO()
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", message=".*pin_memory.*")
                with redirect_stdout(buffer), redirect_stderr(buffer):
                    result = self.funasr_model.generate(
                        input=waveform,
                        cache={},
                        language=self.config.funasr_language,
                        use_itn=self.config.funasr_use_itn,
                        batch_size_s=30,
                        disable_pbar=True,
                    )
            text = self._extract_text_from_funasr_result(result)
            if text:
                return text.replace(" ", "")
        except Exception as exc:
            console_error(f"[VOICE] FunASR 识别失败: {exc}")
        return ""

    @staticmethod
    def _extract_text_from_funasr_result(result: Any) -> str:
        if isinstance(result, list) and result:
            result = result[0]
        if isinstance(result, dict):
            for key in ("text", "preds", "value"):
                value = result.get(key)
                if isinstance(value, str) and value.strip():
                    if rich_transcription_postprocess is not None:
                        try:
                            return rich_transcription_postprocess(value)
                        except Exception:
                            return value
                    return value
        if isinstance(result, str):
            return result
        return ""

    def _recognize_with_vosk(self, audio_data: Any) -> str:
        if self.vosk_recognizer is None:
            return ""
        try:
            raw_pcm = audio_data.get_raw_data(convert_rate=16000, convert_width=2)
            self.vosk_recognizer.AcceptWaveform(raw_pcm)
            result = json.loads(self.vosk_recognizer.FinalResult())
            return str(result.get("text", "")).replace(" ", "")
        except Exception:
            return ""

    def _recognize_with_google(self, audio_data: Any) -> str:
        if not self.config.online_recognition or not self.recognizer or not hasattr(self.recognizer, "recognize_google"):
            return ""
        try:
            return self.recognizer.recognize_google(audio_data, language="zh-CN").replace(" ", "")
        except Exception:
            return ""

    def _recognize_audio_data(self, audio_data: Any) -> str:
        engine = self.config.asr_engine
        if engine in ("auto", "funasr"):
            text = self._recognize_with_funasr(audio_data)
            if text:
                return text
            if engine == "funasr":
                return ""

        if engine in ("auto", "vosk"):
            text = self._recognize_with_vosk(audio_data)
            if text:
                return text
            if engine == "vosk":
                return ""

        if engine in ("auto", "google"):
            return self._recognize_with_google(audio_data)
        return ""

    def _detect_openwakeword(self, audio_data: Any) -> bool:
        if self.openwakeword_model is None:
            return False
        try:
            raw_pcm = audio_data.get_raw_data(convert_rate=16000, convert_width=2)
            samples = np.frombuffer(raw_pcm, dtype=np.int16)
            if hasattr(self.openwakeword_model, "reset"):
                self.openwakeword_model.reset()
            chunk_size = max(320, self.config.openwakeword_chunk_size)
            for idx in range(0, len(samples), chunk_size):
                chunk = samples[idx: idx + chunk_size]
                if len(chunk) < chunk_size:
                    break
                scores = self.openwakeword_model.predict(chunk)
                if isinstance(scores, dict):
                    for score in scores.values():
                        try:
                            if float(score) >= self.config.openwakeword_threshold:
                                return True
                        except Exception:
                            continue
        except Exception as exc:
            console_error(f"[VOICE] openWakeWord 检测失败，将继续使用文本唤醒匹配: {exc}")
        return False

    def _detect_wake_word(self, audio_data: Any, text: str) -> bool:
        if self._detect_openwakeword(audio_data):
            console_info("[VOICE] openWakeWord 已检测到唤醒词")
            return True
        return self._wake_matches(text)

    def _get_working_microphone(self) -> Any | None:
        if not sr:
            return None
        try:
            mic = sr.Microphone()
            with mic as source:
                pass
            return mic
        except Exception as exc:
            console_error(f"默认麦克风不可用，正在扫描其他输入设备: {exc}")

        for idx, name in enumerate(sr.Microphone.list_microphone_names()):
            lowered = str(name).lower()
            if any(marker in lowered for marker in ("output", "speaker", "扬声器", "映射器")):
                continue
            try:
                mic = sr.Microphone(device_index=idx)
                with mic as source:
                    pass
                console_info(f"已切换到备用麦克风 [{idx}] {name}")
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
            console_info(
                f"[VOICE] 当前语音引擎状态: ASR={self._active_asr_engine_name()}, Wake={self._active_wake_engine_name()}, "
                f"FunASRReady={self.funasr_model is not None}, FunASRDevice={self.funasr_runtime_device}, VoskReady={self.vosk_recognizer is not None}, "
                f"OpenWakeWordReady={self.openwakeword_model is not None}"
            )
            console_info(
                f"[VOICE] 语音助手已启动，唤醒词: {self.config.wake_word} | "
                f"ASR: {self._active_asr_engine_name()} | 唤醒: {self._active_wake_engine_name()}"
            )
            console_info("[VOICE] 状态：等待唤醒")
            self._set_session_state("waiting_wake")
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
        self._set_session_state("stopped")

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
                            audio = self.recognizer.listen(
                                source,
                                timeout=1,
                                phrase_time_limit=self.config.wake_phrase_time_limit,
                            )
                            text = self._recognize_audio_data(audio)
                            if text:
                                console_info(f"[VOICE] 唤醒监听识别: {text}")
                            if self._is_stop_playback_command(text):
                                self._stop_playback()
                                continue
                            if self._detect_wake_word(audio, text):
                                self._handle_wake_word()
                        except sr.WaitTimeoutError:
                            pass
                        except Exception:
                            pass
                    else:
                        try:
                            console_info("[VOICE] 正在监听指令...")
                            audio = self.recognizer.listen(
                                source,
                                timeout=self.config.command_timeout,
                                phrase_time_limit=self.config.command_phrase_time_limit,
                            )
                            text = self._recognize_audio_data(audio)
                            if text:
                                console_info(f"[VOICE] 指令识别: {text}")
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
        self._set_session_state("waiting_command")
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
            self._mark_speaking(response)
            speak_async(response)

    def _set_session_state(self, state: str) -> None:
        self.session_state = state

    def _cancel_speaking_timer(self) -> None:
        if self._speak_state_timer is not None:
            try:
                self._speak_state_timer.cancel()
            except Exception:
                pass
            self._speak_state_timer = None

    def _mark_speaking(self, text: str) -> None:
        self._cancel_speaking_timer()
        self._set_session_state("speaking")
        delay = max(1.6, min(8.0, len(str(text or "").strip()) * 0.09))

        def _restore() -> None:
            if self.is_active:
                self._set_session_state("waiting_command")
            else:
                self._set_session_state("waiting_wake")

        timer = threading.Timer(delay, _restore)
        timer.daemon = True
        self._speak_state_timer = timer
        timer.start()

    def _record_round(self, command: str, response: str, source: str, metadata: Optional[dict[str, Any]] = None) -> None:
        payload = dict(self.session_meta)
        if metadata:
            payload.update(metadata)
        record = self.round_archive.record_round(prompt=command, response=response, source=source, metadata=payload)
        self.session_rounds.append(record)

    @staticmethod
    def _extract_note_content(command: str) -> str:
        content = str(command or "")
        for prefix in ("记住", "记一下", "记录一下", "记录", "帮我记录", "请记录", "记到知识库"):
            if prefix in content:
                content = content.split(prefix, 1)[-1]
                break
        return content.strip(" ，。！？,!? \n")

    def _save_note(self, note_content: str) -> bool:
        if not note_content.strip():
            return False
        self.pending_note_items.append(note_content.strip())
        return True

    def _build_full_session_transcript(self) -> str:
        lines = [
            f"语音会话时间：{time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"交互轮次：{len(self.session_rounds)}",
            "",
            "以下为本轮完整语音交互记录：",
        ]
        for index, item in enumerate(self.session_rounds, start=1):
            lines.append(f"{index}. 用户：{str(item.get('prompt', '')).strip()}")
            lines.append(f"   助手：{str(item.get('response', '')).strip()}")
        return "\n".join(lines)

    def _build_user_knowledge_source(self) -> str:
        lines = [
            f"语音会话时间：{time.strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "以下仅为用户在本轮语音交互中的口述内容：",
        ]
        for index, item in enumerate(self.session_rounds, start=1):
            prompt = str(item.get("prompt", "")).strip()
            if prompt:
                lines.append(f"{index}. {prompt}")
        return "\n".join(lines)

    def _extract_knowledge_with_llm(self, transcript: str) -> list[str]:
        if not transcript.strip():
            return []
        prompt = (
            "请仅从以下用户口述内容中提取适合写入实验室知识库的有效知识。"
            "只保留用户明确说出的实验规范、操作经验、风险提示、待办事项、事实记录。"
            "不要写入助手回答、专家模型识别结果、系统提示语、停止播报或结束语音等控制指令。"
            "如果用户口述中没有可沉淀的知识，请输出空数组 []。"
            "请仅输出 JSON 数组字符串，例如 [\"知识1\", \"知识2\"]。"
        )
        try:
            raw = ask_assistant_with_rag(
                frame=None,
                question=f"{prompt}\n\n【用户口述记录】\n{transcript}",
                rag_context="请只做知识提取，不要补充专家结论，也不要自由发挥。",
                model_name=self.ai_backend.get("model", "qwen-vl-max"),
            )
            start = raw.find("[")
            end = raw.rfind("]")
            if start != -1 and end != -1 and end > start:
                payload = json.loads(raw[start : end + 1])
                if isinstance(payload, list):
                    return [str(item).strip() for item in payload if str(item).strip()]
        except Exception as exc:
            console_error(f"[VOICE] 会话知识提取失败: {exc}")

        fallback: list[str] = []
        for note in self.pending_note_items:
            if note.strip():
                fallback.append(f"用户口述记录：{note.strip()}")
        return fallback

    def _finalize_session_summary(self) -> None:
        if not self.session_rounds:
            return
        transcript = self._build_full_session_transcript()
        user_knowledge_source = self._build_user_knowledge_source()
        knowledge_items = self._extract_knowledge_with_llm(user_knowledge_source)
        self.round_archive.write_session_summary(
            transcript,
            knowledge_items=knowledge_items,
            metadata={
                "knowledge_item_count": len(knowledge_items),
                "knowledge_source": "user_voice_only",
            },
        )
        if knowledge_items:
            text = "[语音会话知识提取]\n" + "\n".join(f"- {item}" for item in knowledge_items)
            try:
                _common_memory_engine().save_and_ingest_note(text)
            except Exception as exc:
                console_error(f"[VOICE] 语音会话知识回灌失败: {exc}")

    def _finalize_active_round(self) -> None:
        if not self.session_rounds:
            return
        self._finalize_session_summary()
        self.session_rounds = []
        self.pending_note_items = []

    def _is_stop_session_command(self, text: str) -> bool:
        normalized = self._normalize_text(text)
        session_keywords = (
            "退出",
            "退出助手",
            "关闭语音",
            "结束语音",
            "停止语音",
            "不用了",
            "结束助手",
            "结束对话",
            "退出对话",
            "结束本轮",
        )
        return any(self._normalize_text(keyword) in normalized for keyword in session_keywords)

    def _is_note_command(self, text: str) -> bool:
        normalized = self._normalize_text(text)
        return any(
            self._normalize_text(keyword) in normalized
            for keyword in ("记住", "记一下", "记录一下", "记录", "帮我记录", "请记录", "记到知识库")
        )

    def _match_local_command_intent(self, text: str) -> str | None:
        normalized = self._normalize_text(text)
        command_map = {
            "start_monitor": ("启动监控", "开始监控", "打开监控", "开始巡检", "开始检测"),
            "stop_monitor": ("停止监控", "结束监控", "关闭监控", "停止巡检", "停止检测"),
            "run_self_check": ("系统自检", "运行自检", "执行自检", "开始自检"),
            "open_expert_center": ("打开专家中心", "专家中心", "打开专家", "专家管理"),
            "open_knowledge_center": ("打开知识中心", "知识中心", "打开知识库", "知识库管理"),
            "open_model_config": ("打开模型配置", "模型配置", "模型服务", "打开模型服务"),
            "open_training_center": ("打开训练中心", "训练中心", "打开训练台", "训练工作台"),
            "open_manual": ("打开使用手册", "使用手册", "打开手册", "软件说明"),
            "open_about": ("打开关于系统", "关于系统", "关于软件", "打开关于"),
            "toggle_sidebar": ("切换侧栏", "折叠侧栏", "展开侧栏", "切换界面侧栏"),
            "shutdown_app": ("关闭软件", "退出软件", "关闭系统", "退出程序"),
        }
        for intent, keywords in command_map.items():
            if any(self._normalize_text(keyword) in normalized for keyword in keywords):
                return intent
        return None

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
        keep_active = local_origin
        self._set_session_state("processing")

        try:
            if self._is_stop_playback_command(text):
                self._stop_playback()
                response = "已停止当前语音播报。"
                keep_active = True
                self._deliver_response(response, speak_response=False, reply_callback=reply_callback)
                self._record_round(text, response, source, {**round_meta, "stop_playback": True})
                return response

            if self._is_stop_session_command(text):
                stop_tts()
                self._cancel_speaking_timer()
                response = "好的，已结束本轮语音交互，等待你再次唤醒。"
                self._deliver_response(response, speak_response=speak_response, reply_callback=reply_callback)
                self._record_round(text, response, source, {**round_meta, "stop_session": True})
                self._finalize_active_round()
                keep_active = False
                return response

            local_intent = self._match_local_command_intent(text)
            if local_origin and local_intent and self.local_command_handler is not None:
                try:
                    response = str(self.local_command_handler(text, local_intent) or "").strip()
                except Exception as exc:
                    response = f"本地界面指令执行失败：{exc}"
                    console_error(f"[VOICE] 本地界面指令执行失败: {exc}")
                if not response:
                    response = "好的，界面指令已执行。"
                keep_active = True
                self._deliver_response(response, speak_response=speak_response, reply_callback=reply_callback)
                self._record_round(text, response, source, {**round_meta, "local_intent": local_intent})
                return response

            if self._is_note_command(text):
                note_content = self._extract_note_content(text)
                if note_content:
                    saved = self._save_note(note_content)
                    response = "已记录本轮语音内容，将在本轮结束后整理写入知识库。" if saved else "记录失败，请稍后重试。"
                    self._deliver_response(response, speak_response=speak_response, reply_callback=reply_callback)
                    self._record_round(text, response, source, {**round_meta, "note_saved": saved})
                    keep_active = True
                    return response

            current_frame = self.get_latest_frame_callback() if self.get_latest_frame_callback else None
            orchestrated = orchestrator.plan_voice_command(
                text,
                source=source,
                frame=current_frame,
                model_name=self.ai_backend.get("model", "qwen-vl-max"),
                context=round_meta,
            )
            response = str(orchestrated.text or "").strip()
            if not response:
                response = "当前未生成有效响应，请稍后重试。"
            keep_active = True
            self._deliver_response(response, speak_response=speak_response, reply_callback=reply_callback)
            self._record_round(
                text,
                response,
                source,
                {
                    **round_meta,
                    "orchestrator_intent": orchestrated.intent,
                    "orchestrator_actions": list(orchestrated.actions),
                    **dict(orchestrated.metadata or {}),
                },
            )
            return response
        except Exception as exc:
            error_text = f"语音指令处理失败: {exc}"
            console_error(error_text)
            self._deliver_response(error_text, speak_response=False, reply_callback=reply_callback)
            self._record_round(text, error_text, source, {**round_meta, "error": True})
            return error_text
        finally:
            if local_origin:
                self.is_active = keep_active
                if keep_active:
                    self.last_wake_time = time.time()
                    self._set_session_state("waiting_command")
                else:
                    self._set_session_state("waiting_wake")

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
_remote_text_router: Optional[VoiceInteraction] = None
_pending_local_command_handler: Optional[Callable[[str, str], Optional[str]]] = None


def set_voice_local_command_handler(handler: Optional[Callable[[str, str], Optional[str]]]) -> None:
    global _pending_local_command_handler
    _pending_local_command_handler = handler
    if _voice_interaction is not None:
        _voice_interaction.set_local_command_handler(handler)


def get_voice_interaction() -> Optional[VoiceInteraction]:
    global _voice_interaction
    if not VOICE_INTERACTION_AVAILABLE:
        return None
    if _voice_interaction is None:
        _voice_interaction = VoiceInteraction()
        if _pending_local_command_handler is not None:
            _voice_interaction.set_local_command_handler(_pending_local_command_handler)
    return _voice_interaction


def get_remote_text_router() -> Optional[VoiceInteraction]:
    """返回仅用于远端文本指令处理的轻量语音路由器。"""
    global _remote_text_router
    if _remote_text_router is None:
        _remote_text_router = VoiceInteraction(initialize_audio_models=False)
    return _remote_text_router

