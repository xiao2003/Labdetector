import unittest

from pc.core.expert_manager import expert_manager


class ExpertCapabilityFactsTests(unittest.TestCase):
    def test_capability_facts_expose_required_routing_fields(self) -> None:
        rows = expert_manager.list_expert_capability_facts()

        self.assertTrue(rows)
        for row in rows:
            self.assertIn("expert_code", row)
            self.assertIn("trigger_mode", row)
            self.assertIn("media_types", row)
            self.assertIn("voice_keywords", row)
            self.assertIn("event_names", row)
            self.assertIn("knowledge_required", row)
            self.assertIn("knowledge_scope", row)
            self.assertIn("knowledge_ready", row)
            self.assertIn("default_speak_policy", row)


if __name__ == "__main__":
    unittest.main()
