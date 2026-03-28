import unittest

from pi.voice.interaction import PiVoiceInteraction


class _FakeRecognizer:
    def __init__(self, outputs):
        self.outputs = list(outputs)

    def recognize_stream(self, _audio_data: bytes):
        if not self.outputs:
            return ""
        return self.outputs.pop(0)


class PiVoiceInteractionTest(unittest.TestCase):
    def test_wake_alias_can_activate_interaction(self):
        recognizer = _FakeRecognizer(["小爱"])
        interaction = PiVoiceInteraction(
            recognizer,
            wake_word="小爱同学",
            wake_aliases=["小爱", "小艾同学"],
        )

        event = interaction.process_audio(b"wake")
        self.assertEqual("EVENT:WOKEN", event)
        self.assertTrue(interaction.is_active)

    def test_stop_command_can_interrupt_playback_state(self):
        recognizer = _FakeRecognizer(["停止播报"])
        interaction = PiVoiceInteraction(recognizer, wake_word="小爱同学")
        interaction.is_active = True

        event = interaction.process_audio(b"stop")
        self.assertEqual("EVENT:STOP_TTS", event)
        self.assertFalse(interaction.is_active)


if __name__ == "__main__":
    unittest.main()
