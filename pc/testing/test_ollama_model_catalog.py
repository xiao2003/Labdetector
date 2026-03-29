import unittest
from unittest.mock import patch

from pc.core.ai_backend import configured_model_catalog, ollama_runtime_env
from pc.core.runtime_assets import DEFAULT_OLLAMA_MODELS, ollama_asset_root


class OllamaModelCatalogTests(unittest.TestCase):
    def test_configured_model_catalog_keeps_builtin_qwen_models_without_local_install(self) -> None:
        with patch("pc.core.ai_backend.list_ollama_models", return_value=[]):
            catalog = configured_model_catalog()

        self.assertEqual(catalog["ollama"], DEFAULT_OLLAMA_MODELS)
        self.assertIn("qwen3.5:4b", catalog["ollama"])
        self.assertIn("qwen3.5:9b", catalog["ollama"])
        self.assertIn("qwen3.5:27b", catalog["ollama"])
        self.assertIn("qwen3.5:35b", catalog["ollama"])

    def test_configured_model_catalog_merges_local_models_with_builtin_qwen_models(self) -> None:
        with patch("pc.core.ai_backend.list_ollama_models", return_value=["phi4:14b", "qwen3.5:9b"]):
            catalog = configured_model_catalog()

        self.assertEqual(catalog["ollama"][0], "phi4:14b")
        self.assertIn("qwen3.5:4b", catalog["ollama"])
        self.assertIn("qwen3.5:9b", catalog["ollama"])
        self.assertIn("qwen3.5:27b", catalog["ollama"])
        self.assertIn("qwen3.5:35b", catalog["ollama"])

    def test_ollama_runtime_env_points_models_to_project_runtime_dir(self) -> None:
        env = ollama_runtime_env()
        self.assertEqual(env["OLLAMA_MODELS"], str(ollama_asset_root()))


if __name__ == "__main__":
    unittest.main()
