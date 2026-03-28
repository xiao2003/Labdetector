import unittest
from pathlib import Path
from unittest.mock import patch

from pc.core.orchestrator_runtime import (
    OrchestratorRuntimeError,
    _extract_first_json_object,
    get_runtime_status,
)


class OrchestratorRuntimeTests(unittest.TestCase):
    def test_runtime_status_reports_missing_assets(self) -> None:
        with patch("pc.core.orchestrator_runtime.runtime_binary_path", return_value=Path("D:/missing/llama-cli.exe")), \
             patch("pc.core.orchestrator_runtime.model_binary_path", return_value=Path("D:/missing/model.gguf")):
            status = get_runtime_status()

        self.assertTrue(status.enabled)
        self.assertFalse(status.ready)
        self.assertIn("缺少", status.reason)

    def test_extract_first_json_object_from_wrapped_output(self) -> None:
        payload = _extract_first_json_object('前导文本 {"intent":"call_expert_voice","expert_codes":["a"]} 尾部')
        self.assertEqual(payload["intent"], "call_expert_voice")
        self.assertEqual(payload["expert_codes"], ["a"])

    def test_extract_first_json_object_rejects_invalid_output(self) -> None:
        with self.assertRaises(OrchestratorRuntimeError):
            _extract_first_json_object("not-json")


if __name__ == "__main__":
    unittest.main()
