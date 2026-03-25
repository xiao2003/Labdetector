from __future__ import annotations

import asyncio
import unittest
from pathlib import Path
from unittest.mock import patch

from pi import pisend_receive
from pi.config import get_pi_path_config


class _FakeStream:
    def start_stream(self) -> None:
        return None

    def read(self, *_args, **_kwargs) -> bytes:
        raise RuntimeError("stop")

    def stop_stream(self) -> None:
        return None

    def close(self) -> None:
        return None


class _FakePyAudioInstance:
    def open(self, **_kwargs):
        return _FakeStream()

    def terminate(self) -> None:
        return None


class _FakePyAudioModule:
    paInt16 = 8

    def PyAudio(self):
        return _FakePyAudioInstance()


class _FakeInteraction:
    def __init__(self, recognizer, wake_word="小爱同学"):
        self.recognizer = recognizer
        self.wake_word = wake_word
        self.is_active = False

    def process_audio(self, _data: bytes):
        return None


class _FakeWebSocket:
    async def send(self, _message: str) -> None:
        return None


class VoiceModelPathTests(unittest.TestCase):
    def test_get_pi_path_config_resolves_relative_model_dir(self) -> None:
        resolved = get_pi_path_config("voice.model_path", "voice/model")
        expected = Path(__file__).resolve().parents[1] / "voice" / "model"
        self.assertEqual(Path(resolved), expected)

    def test_voice_thread_uses_configured_model_path(self) -> None:
        captured = {}

        class _FakeRecognizer:
            def __init__(self, model_path: str):
                captured["model_path"] = model_path

        previous_running = pisend_receive.running
        pisend_receive.running = True
        try:
            with patch.object(pisend_receive, "PiVoiceRecognizer", _FakeRecognizer), \
                 patch.object(pisend_receive, "PiVoiceInteraction", _FakeInteraction), \
                 patch.object(pisend_receive, "pyaudio", _FakePyAudioModule()), \
                 patch.object(pisend_receive, "console_info", lambda *_args, **_kwargs: None):
                asyncio.run(pisend_receive.voice_thread(_FakeWebSocket()))
        finally:
            pisend_receive.running = previous_running

        expected = str(Path(__file__).resolve().parents[1] / "voice" / "model")
        self.assertEqual(captured.get("model_path"), expected)

    def test_self_check_and_runtime_share_same_download_target(self) -> None:
        targets = []

        def _fake_downloader(target_dir: str) -> bool:
            targets.append(target_dir)
            return True

        previous_loader = pisend_receive._load_runtime_modules
        previous_downloader = pisend_receive.check_and_download_vosk
        previous_detect = pisend_receive.detect_audio_capabilities
        previous_picamera = pisend_receive.PICAMERA_AVAILABLE
        pisend_receive._load_runtime_modules = lambda: None
        pisend_receive.check_and_download_vosk = _fake_downloader
        pisend_receive.detect_audio_capabilities = lambda: (False, False)
        pisend_receive.PICAMERA_AVAILABLE = False
        try:
            ok = pisend_receive.run_pi_self_check(auto_install=False)
            self.assertTrue(ok)
        finally:
            pisend_receive._load_runtime_modules = previous_loader
            pisend_receive.check_and_download_vosk = previous_downloader
            pisend_receive.detect_audio_capabilities = previous_detect
            pisend_receive.PICAMERA_AVAILABLE = previous_picamera

        expected = str(Path(__file__).resolve().parents[1] / "voice" / "model")
        self.assertEqual(targets, [expected])


if __name__ == "__main__":
    unittest.main()
