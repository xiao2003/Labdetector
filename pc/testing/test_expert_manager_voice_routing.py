import unittest
from types import SimpleNamespace

from pc.core.expert_manager import ExpertManager


class _FakeExpert:
    def __init__(self, code: str, event_name: str) -> None:
        self.expert_code = code
        self.expert_name = code
        self.expert_version = "test"
        self._event_name = event_name

    def supported_events(self):
        return [self._event_name]


class ExpertManagerVoiceRoutingTests(unittest.TestCase):
    def test_forced_expert_codes_bypass_keyword_matching(self) -> None:
        manager = ExpertManager.__new__(ExpertManager)
        expert = _FakeExpert("safety.ppe_expert", "PPE穿戴检查")
        definition = SimpleNamespace(
            code="safety.ppe_expert",
            trigger_mode="voice",
            event_names=["PPE穿戴检查"],
            stream_group="safety",
            voice_keywords=("护目镜",),
        )

        manager._iter_loaded_with_definition = lambda: [(expert, definition)]
        manager.route_and_analyze = lambda event_name, frame, context, **kwargs: f"分析:{event_name}"

        result = ExpertManager.route_voice_command(
            manager,
            "完全不包含关键词的指令",
            frame=None,
            context={"source": "pi:test"},
            forced_expert_codes=["safety.ppe_expert"],
        )

        self.assertEqual(result["matched_expert_codes"], ["safety.ppe_expert"])
        self.assertEqual(result["text"], "分析:PPE穿戴检查")

    def test_without_forced_codes_still_requires_keyword_match(self) -> None:
        manager = ExpertManager.__new__(ExpertManager)
        expert = _FakeExpert("safety.ppe_expert", "PPE穿戴检查")
        definition = SimpleNamespace(
            code="safety.ppe_expert",
            trigger_mode="voice",
            event_names=["PPE穿戴检查"],
            stream_group="safety",
            voice_keywords=("护目镜",),
        )

        manager._iter_loaded_with_definition = lambda: [(expert, definition)]
        manager.route_and_analyze = lambda event_name, frame, context, **kwargs: f"分析:{event_name}"

        result = ExpertManager.route_voice_command(
            manager,
            "完全不包含关键词的指令",
            frame=None,
            context={"source": "pi:test"},
        )

        self.assertEqual(result["matched_expert_codes"], [])
        self.assertEqual(result["text"], "")


if __name__ == "__main__":
    unittest.main()
