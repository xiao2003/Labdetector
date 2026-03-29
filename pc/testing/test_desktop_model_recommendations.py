import unittest

from pc.desktop_app import DesktopApp


class DesktopModelRecommendationTests(unittest.TestCase):
    def test_recommended_models_keep_builtin_qwen_entries_visible(self) -> None:
        app = DesktopApp.__new__(DesktopApp)
        app.current_state = {"session": {}}

        models = app._recommended_models_for_backend("ollama", ["phi4:14b"])

        self.assertIn("qwen3.5:4b", models)
        self.assertIn("qwen3.5:9b", models)
        self.assertIn("qwen3.5:27b", models)
        self.assertIn("qwen3.5:35b", models)
        self.assertIn("phi4:14b", models)


if __name__ == "__main__":
    unittest.main()
