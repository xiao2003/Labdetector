import unittest
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

from pc.core.orchestrator_runtime import (
    OrchestratorRuntimeError,
    _extract_first_json_object,
    prepare_orchestrator_assets,
    get_runtime_status,
    STATE_WARMING_UP,
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

    def test_prepare_timeout_keeps_warming_up_state(self) -> None:
        with tempfile.TemporaryDirectory(prefix="orchestrator_runtime_test_") as temp_dir:
            temp_root = Path(temp_dir)
            runtime_path = temp_root / "runtime" / "llama-cli.exe"
            model_path = temp_root / "model" / "model.gguf"
            state_path = temp_root / "state.json"
            runtime_path.parent.mkdir(parents=True, exist_ok=True)
            model_path.parent.mkdir(parents=True, exist_ok=True)
            runtime_path.write_text("stub", encoding="utf-8")
            model_path.write_text("stub", encoding="utf-8")
            manifest = {
                "runtime": {"version": "test"},
                "model": {"filename": "model.gguf"},
            }
            with patch("pc.core.orchestrator_runtime.get_config", side_effect=lambda key, default=None: True if key == "orchestrator.enabled" else default), \
                 patch("pc.core.orchestrator_runtime.load_asset_manifest", return_value=manifest), \
                 patch("pc.core.orchestrator_runtime.orchestrator_state_path", return_value=state_path), \
                 patch("pc.core.orchestrator_runtime.runtime_binary_path", return_value=runtime_path), \
                 patch("pc.core.orchestrator_runtime.model_binary_path", return_value=model_path), \
                 patch("pc.core.orchestrator_runtime.warm_up_orchestrator_runtime", side_effect=subprocess.TimeoutExpired(["llama-cli"], 90)):
                payload = prepare_orchestrator_assets()

        self.assertEqual(payload["status"], STATE_WARMING_UP)
        self.assertEqual(payload["planner_backend"], "deterministic")

    def test_prepare_repairs_missing_runtime_and_model(self) -> None:
        with tempfile.TemporaryDirectory(prefix="orchestrator_runtime_repair_") as temp_dir:
            temp_root = Path(temp_dir)
            runtime_path = temp_root / "runtime" / "llama-cli.exe"
            model_path = temp_root / "model" / "Qwen3.5-0.8B.q4_k_m.gguf"
            state_path = temp_root / "state.json"
            manifest = {
                "runtime": {"version": "test"},
                "model": {"filename": "Qwen3.5-0.8B.q4_k_m.gguf"},
            }

            def _fake_materialize_runtime(destination_dir: Path, *, log_callback=None):
                destination_dir.mkdir(parents=True, exist_ok=True)
                (destination_dir / "llama-cli.exe").write_text("stub", encoding="utf-8")
                return {"runtime_dir": str(destination_dir), "copied_files": ["llama-cli.exe"]}

            def _fake_materialize_model(destination_path: Path, *, log_callback=None):
                destination_path.parent.mkdir(parents=True, exist_ok=True)
                destination_path.write_text("stub", encoding="utf-8")
                return {"model_path": str(destination_path)}

            with patch("pc.core.orchestrator_runtime.get_config", side_effect=lambda key, default=None: True if key == "orchestrator.enabled" else default), \
                 patch("pc.core.orchestrator_runtime.load_asset_manifest", return_value=manifest), \
                 patch("pc.core.orchestrator_runtime.orchestrator_state_path", return_value=state_path), \
                 patch("pc.core.orchestrator_runtime.runtime_binary_path", return_value=runtime_path), \
                 patch("pc.core.orchestrator_runtime.model_binary_path", return_value=model_path), \
                 patch("pc.core.orchestrator_runtime.materialize_runtime_bundle", side_effect=_fake_materialize_runtime), \
                 patch("pc.core.orchestrator_runtime.materialize_model_bundle", side_effect=_fake_materialize_model), \
                 patch("pc.core.orchestrator_runtime.warm_up_orchestrator_runtime", return_value=None):
                payload = prepare_orchestrator_assets()
                self.assertTrue(runtime_path.exists())
                self.assertTrue(model_path.exists())

        self.assertEqual(payload["status"], "ready")
        self.assertEqual(payload["planner_backend"], "embedded_model")


if __name__ == "__main__":
    unittest.main()
