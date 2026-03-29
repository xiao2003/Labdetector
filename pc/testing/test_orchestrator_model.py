import unittest
from unittest.mock import patch

from pc.core.orchestrator_model import infer_edge_plan, infer_voice_plan
from pc.core.orchestrator_runtime import OrchestratorRuntimeError


class OrchestratorModelTests(unittest.TestCase):
    def test_infer_voice_plan_normalizes_payload(self) -> None:
        with patch(
            "pc.core.orchestrator_model.invoke_orchestrator_model",
            return_value={
                "intent": "call_expert_voice",
                "expert_codes": "safety.ppe_expert",
                "app_intent": "",
                "need_knowledge": True,
                "speak_policy": "speak_now",
                "summary": "查看 PPE 风险",
            },
        ):
            plan = infer_voice_plan("看一下当前 PPE 风险", source="pi:test", context={"pi_id": "pi-1"})

        self.assertIsNotNone(plan)
        self.assertEqual(plan["intent"], "call_expert_voice")
        self.assertEqual(plan["expert_codes"], ["safety.ppe_expert"])
        self.assertEqual(plan["app_intent"], "")
        self.assertTrue(plan["need_knowledge"])
        self.assertEqual(plan["speak_policy"], "speak_now")

    def test_infer_voice_plan_preserves_app_action_intent(self) -> None:
        with patch(
            "pc.core.orchestrator_model.invoke_orchestrator_model",
            return_value={
                "intent": "open_view",
                "app_intent": "open_training_center",
                "expert_codes": [],
                "need_knowledge": False,
                "speak_policy": "speak_now",
                "summary": "好的，正在打开训练中心。",
            },
        ):
            plan = infer_voice_plan("打开训练中心", source="pc_local", context={})

        self.assertIsNotNone(plan)
        self.assertEqual(plan["intent"], "open_view")
        self.assertEqual(plan["app_intent"], "open_training_center")

    def test_infer_edge_plan_returns_none_when_runtime_unavailable(self) -> None:
        with patch(
            "pc.core.orchestrator_model.invoke_orchestrator_model",
            side_effect=OrchestratorRuntimeError("boom"),
        ):
            plan = infer_edge_plan("危化品识别", context={"pi_id": "pi-1"})

        self.assertIsNone(plan)


if __name__ == "__main__":
    unittest.main()
