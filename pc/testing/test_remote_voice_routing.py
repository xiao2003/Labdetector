from __future__ import annotations

import unittest
from unittest.mock import patch

from pc.voice.voice_interaction import VoiceInteraction


class RemoteVoiceRoutingTests(unittest.TestCase):
    def test_remote_command_does_not_trigger_local_gui_handler(self) -> None:
        agent = VoiceInteraction(initialize_audio_models=False)
        calls = []
        agent.set_local_command_handler(lambda text, intent: calls.append((text, intent)) or "已执行本地指令")

        with patch('pc.voice.voice_interaction._build_voice_rag_context', return_value=''), \
             patch('pc.voice.voice_interaction.ask_assistant_with_rag', return_value='远端问答回复'):
            reply = agent.process_remote_command('1', '打开训练中心')

        self.assertEqual(reply, '远端问答回复')
        self.assertEqual(calls, [])

    def test_local_command_still_triggers_local_gui_handler(self) -> None:
        agent = VoiceInteraction(initialize_audio_models=False)
        calls = []
        agent.set_local_command_handler(lambda text, intent: calls.append((text, intent)) or '已打开训练中心')

        reply = agent.process_text_command('打开训练中心', source='pc_local', speak_response=False)

        self.assertEqual(reply, '已打开训练中心')
        self.assertEqual(calls, [('打开训练中心', 'open_training_center')])


if __name__ == '__main__':
    unittest.main()
