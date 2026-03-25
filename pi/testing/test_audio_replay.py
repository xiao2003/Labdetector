from __future__ import annotations

import unittest
from pathlib import Path

from pi.testing.audio_assets import ensure_fixed_voice_fixtures
from pi.testing.audio_replay import replay_voice_plan
from pi.voice.interaction import PiVoiceInteraction
from pi.voice.recognizer import PiVoiceRecognizer


class AudioReplayTests(unittest.TestCase):
    def test_fixed_wav_can_drive_vosk_replay(self) -> None:
        model_path = Path(__file__).resolve().parents[1] / "voice" / "model"
        if not (model_path / "am").exists():
            self.skipTest("本地 Vosk 模型不存在，跳过真实音频回放测试。")

        fixed = ensure_fixed_voice_fixtures()
        wake_fixture = Path(__file__).resolve().parents[2] / "pc" / "testing" / "assets" / "audio_fixtures" / "wake_word.wav"
        result = replay_voice_plan(
            recognizer_cls=PiVoiceRecognizer,
            interaction_cls=PiVoiceInteraction,
            model_path=str(model_path),
            wake_word="小爱同学",
            sample_plan=[
                {
                    "sample_id": "wake_word",
                    "path": str(wake_fixture),
                    "text": "小爱同学",
                    "category": "wake_word",
                    "expected_keywords": ["小爱同学"],
                    "speaker_type": "fixed_fixture",
                },
                {
                    "sample_id": "fixed_qa_status",
                    "path": fixed["qa_status"],
                    "text": "介绍当前系统状态",
                    "category": "qa",
                    "expected_keywords": ["系统", "状态"],
                    "speaker_type": "fixed_fixture",
                },
            ],
        )

        records = result["records"]
        self.assertEqual(len(records), 2)
        self.assertIn("EVENT:WOKEN", records[0]["emitted"])
        self.assertTrue(records[1]["recognized_texts"])
        self.assertTrue(records[1]["keyword_match"])
        outgoing = result["outgoing_messages"]
        self.assertEqual(outgoing[0]["payload"], "PI_EVENT:WOKEN")
        self.assertTrue(any(row["payload"].startswith("PI_VOICE_COMMAND:") for row in outgoing))


if __name__ == "__main__":
    unittest.main()
