from __future__ import annotations

import unittest
from unittest.mock import patch

from pc.core.orchestrator import OrchestratorResult
from pc.voice import voice_interaction as voice_module
from pc.voice.voice_interaction import VoiceInteraction, get_remote_text_router, set_voice_local_command_handler


class RemoteVoiceRoutingTests(unittest.TestCase):
    def tearDown(self) -> None:
        voice_module._remote_text_router = None
        voice_module._pending_local_command_handler = None

    def test_remote_command_does_not_trigger_local_gui_handler(self) -> None:
        agent = VoiceInteraction(initialize_audio_models=False)
        calls = []
        agent.set_local_command_handler(lambda text, intent: calls.append((text, intent)) or "已执行本地指令")

        with patch(
            "pc.voice.voice_interaction.orchestrator.plan_voice_command",
            return_value=OrchestratorResult(
                intent="answer_from_knowledge",
                text="远端问答回复",
                actions=[{"type": "answer_from_knowledge"}],
                metadata={"planner_backend": "test"},
            ),
        ):
            reply = agent.process_remote_command('1', '打开训练中心')

        self.assertEqual(reply, '远端问答回复')
        self.assertEqual(calls, [])

    def test_remote_command_can_trigger_app_internal_action_via_orchestrator(self) -> None:
        agent = VoiceInteraction(initialize_audio_models=False)
        calls = []
        agent.set_local_command_handler(lambda text, intent: calls.append((text, intent)) or "已打开训练中心")

        with patch(
            "pc.voice.voice_interaction.orchestrator.plan_voice_command",
            return_value=OrchestratorResult(
                intent="app_action",
                text="好的，正在打开训练中心。",
                actions=[{"type": "app_action", "intent": "open_training_center"}],
                metadata={"planner_backend": "test"},
            ),
        ):
            reply = agent.process_remote_command("1", "打开训练中心")

        self.assertEqual(reply, "已打开训练中心")
        self.assertEqual(calls, [("打开训练中心", "open_training_center")])

    def test_local_command_still_triggers_local_gui_handler(self) -> None:
        agent = VoiceInteraction(initialize_audio_models=False)
        calls = []
        agent.set_local_command_handler(lambda text, intent: calls.append((text, intent)) or '已打开训练中心')

        with patch(
            "pc.voice.voice_interaction.orchestrator.plan_voice_command",
            return_value=OrchestratorResult(
                intent="app_action",
                text="好的，正在打开训练中心。",
                actions=[{"type": "app_action", "intent": "open_training_center"}],
                metadata={"planner_backend": "test"},
            ),
        ):
            reply = agent.process_text_command('打开训练中心', source='pc_local', speak_response=False)

        self.assertEqual(reply, '已打开训练中心')
        self.assertEqual(calls, [('打开训练中心', 'open_training_center')])

    def test_remote_text_router_inherits_global_local_handler(self) -> None:
        calls = []
        set_voice_local_command_handler(lambda text, intent: calls.append((text, intent)) or "系统自检已发起")
        agent = get_remote_text_router()

        with patch(
            "pc.voice.voice_interaction.orchestrator.plan_voice_command",
            return_value=OrchestratorResult(
                intent="app_action",
                text="好的，正在执行系统自检。",
                actions=[{"type": "app_action", "intent": "run_self_check"}],
                metadata={"planner_backend": "test"},
            ),
        ):
            reply = agent.process_remote_command("1", "介绍当前系统状态")

        self.assertEqual(reply, "系统自检已发起")
        self.assertEqual(calls, [("介绍当前系统状态", "run_self_check")])


if __name__ == '__main__':
    unittest.main()
