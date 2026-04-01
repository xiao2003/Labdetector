from __future__ import annotations

import unittest
from unittest.mock import patch

import pc.webui.runtime as runtime_module
from pc.webui.runtime import LabDetectorRuntime


class RuntimeSelfHealTests(unittest.TestCase):
    def test_run_self_check_rechecks_after_orchestrator_repair(self) -> None:
        runtime = LabDetectorRuntime()
        config_values = {
            "self_check.pc_auto_install_core": True,
            "self_check.pc_auto_install_training": True,
            "self_check.pc_auto_install_optional": False,
            "self_check.pc_auto_install_voice_ai": True,
            "self_check.pc_auto_install_gpu_runtime": True,
            "self_check.pc_auto_install_ollama": True,
        }
        progress_rows = []
        repair_flags: list[bool] = []

        def _fake_get_config(key: str, default=None):
            return config_values.get(key, default)

        def _fake_set_config(key: str, value) -> None:
            config_values[key] = value

        def _fake_orchestrator_check(*, auto_repair: bool = True):
            repair_flags.append(auto_repair)
            if auto_repair:
                runtime.orchestrator_state = {
                    "status": "ready",
                    "planner_backend": "embedded_model",
                    "reason": "固定管家层已就绪",
                }
                return {
                    "status": "pass",
                    "summary": "固定管家层已自动补齐并恢复 embedded_model",
                    "detail": "固定管家层已就绪",
                    "raw_output": "[INFO] fixed orchestrator runtime",
                }
            return {
                "status": "pass",
                "summary": "固定管家层运行时已就绪",
                "detail": "固定管家层已就绪",
                "raw_output": "[INFO] orchestrator runtime ready",
            }

        pass_result = {
            "status": "pass",
            "summary": "检查通过",
            "detail": "ok",
            "raw_output": "[INFO] pass",
        }

        with patch.object(runtime_module, "get_config", side_effect=_fake_get_config), \
             patch.object(runtime_module, "set_config", side_effect=_fake_set_config), \
             patch.object(LabDetectorRuntime, "_check_dependencies", return_value=dict(pass_result)), \
             patch.object(LabDetectorRuntime, "_check_ollama_runtime", return_value=dict(pass_result)), \
             patch.object(LabDetectorRuntime, "_check_gpu", return_value=dict(pass_result)), \
             patch.object(LabDetectorRuntime, "_check_training_runtime", return_value=dict(pass_result)), \
             patch.object(LabDetectorRuntime, "_check_rag_assets", return_value=dict(pass_result)), \
             patch.object(LabDetectorRuntime, "_check_orchestrator_assets", side_effect=_fake_orchestrator_check):
            results = runtime.run_self_check(progress_callback=progress_rows.append, include_voice_assets=False)

        self.assertTrue(runtime.self_check_has_run)
        self.assertEqual(repair_flags, [True, False])
        self.assertIn("embedded_model", runtime.orchestrator_state.get("planner_backend", ""))
        self.assertTrue(any(str(row.get("stage")) == "recheck" for row in progress_rows))
        self.assertTrue(any(str(row.get("stage")) == "done" and str(row.get("status")) == "success" for row in progress_rows))
        orchestrator_rows = [row for row in results if str(row.get("key")) == "orchestrator_assets"]
        self.assertEqual(len(orchestrator_rows), 1)
        self.assertEqual(orchestrator_rows[0]["status"], "pass")

    def test_check_dependencies_auto_installs_missing_core_packages(self) -> None:
        runtime = LabDetectorRuntime()
        missing_rows = [
            ["numpy", "opencv-python"],
            [],
        ]

        with patch.object(runtime_module, "get_config", side_effect=lambda key, default=None: True if key == "self_check.pc_auto_install_core" else default), \
             patch.object(runtime_module, "resolve_training_python_executable", return_value="C:/Python/python.exe"), \
             patch.object(runtime_module, "build_training_python_env", return_value={"PYTHONIOENCODING": "utf-8"}), \
             patch.object(runtime_module, "install_target_for_training_packages", return_value=None), \
             patch.object(LabDetectorRuntime, "_missing_dependencies", side_effect=lambda module_map: missing_rows.pop(0)), \
             patch.object(
                 LabDetectorRuntime,
                 "_install_python_packages",
                 return_value={
                     "ok": True,
                     "installed": ["numpy", "opencv-python"],
                     "failed": [],
                     "logs": [
                         "[INFO] 开始自动安装Core dependencies: numpy, opencv-python",
                         "[INFO] 安装成功: numpy",
                         "[INFO] 安装成功: opencv-python",
                     ],
                 },
             ):
            result = runtime._check_dependencies()

        self.assertEqual(result["status"], "pass")
        self.assertIn("9 core packages ready", str(result.get("summary")))
        self.assertIn("安装成功: numpy", str(result.get("raw_output")))
        self.assertIn("安装成功: opencv-python", str(result.get("raw_output")))

    def test_check_voice_ai_runtime_auto_installs_missing_packages(self) -> None:
        runtime = LabDetectorRuntime()
        missing_rows = [
            ["funasr"],
            [],
        ]

        with patch.object(runtime_module, "get_config", side_effect=lambda key, default=None: True if key == "self_check.pc_auto_install_voice_ai" else default), \
             patch.object(runtime_module, "resolve_training_python_executable", return_value="C:/Python/python.exe"), \
             patch.object(runtime_module, "build_training_python_env", return_value={"PYTHONIOENCODING": "utf-8"}), \
             patch.object(runtime_module, "install_target_for_training_packages", return_value=None), \
             patch.object(LabDetectorRuntime, "_missing_dependencies", side_effect=lambda module_map: missing_rows.pop(0)), \
             patch.object(
                 LabDetectorRuntime,
                 "_install_python_packages",
                 return_value={
                     "ok": True,
                     "installed": ["funasr"],
                     "failed": [],
                     "logs": [
                         "[INFO] 开始自动安装Voice AI dependencies: funasr",
                         "[INFO] 安装成功: funasr",
                     ],
                 },
             ):
            result = runtime._check_voice_ai_runtime()

        self.assertEqual(result["status"], "pass")
        self.assertIn("增强语音识别运行时已就绪", str(result.get("summary")))
        self.assertIn("安装成功: funasr", str(result.get("raw_output")))

    def test_check_ollama_runtime_auto_installs_when_missing(self) -> None:
        runtime = LabDetectorRuntime()
        found_paths = ["", "C:/Program Files/Ollama/ollama.exe"]

        with patch.object(runtime_module, "get_config", side_effect=lambda key, default=None: True if key == "self_check.pc_auto_install_ollama" else default), \
             patch.object(LabDetectorRuntime, "_find_ollama_executable", side_effect=lambda: found_paths.pop(0) if found_paths else "C:/Program Files/Ollama/ollama.exe"), \
             patch.object(
                 LabDetectorRuntime,
                 "_install_ollama_runtime",
                 return_value={
                     "ok": True,
                     "output": "installed",
                     "command": "winget install Ollama.Ollama",
                 },
             ):
            result = runtime._check_ollama_runtime()

        self.assertEqual(result["status"], "pass")
        self.assertIn("Ollama 已自动补齐", str(result.get("summary")))
        self.assertIn("winget install Ollama.Ollama", str(result.get("raw_output")))


if __name__ == "__main__":
    unittest.main()
