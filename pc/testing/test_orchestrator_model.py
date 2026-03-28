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
                "need_knowledge": True,
                "speak_policy": "speak_now",
                "summary": "查看 PPE 风险",
            },
        ):
            plan = infer_voice_plan("看一下当前 PPE 风险", source="pi:test", context={"pi_id": "pi-1"})

        self.assertIsNotNone(plan)
        self.assertEqual(plan["intent"], "call_expert_voice")
        self.assertEqual(plan["expert_codes"], ["safety.ppe_expert"])
        self.assertTrue(plan["need_knowledge"])
        self.assertEqual(plan["speak_policy"], "speak_now")

    def test_infer_edge_plan_returns_none_when_runtime_unavailable(self) -> None:
        with patch(
            "pc.core.orchestrator_model.invoke_orchestrator_model",
            side_effect=OrchestratorRuntimeError("boom"),
        ):
            plan = infer_edge_plan("危化品识别", context={"pi_id": "pi-1"})

        self.assertIsNone(plan)


if __name__ == "__main__":
    unittest.main()
