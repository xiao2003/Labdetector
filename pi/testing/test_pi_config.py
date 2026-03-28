from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pi import config


class PiConfigTest(unittest.TestCase):
    def test_defaults_include_wake_aliases_and_light_frontend_role(self) -> None:
        with tempfile.TemporaryDirectory(prefix="neurolab_pi_config_") as temp_dir:
            config_path = Path(temp_dir) / "config.ini"
            with mock.patch.object(config.PiConfig, "_config", None), \
                 mock.patch.object(config.PiConfig, "_config_path", str(config_path)):
                config.PiConfig.init()

                wake_aliases = config.get_pi_config("voice.wake_aliases", "")
                node_role = config.get_pi_config("architecture.node_role", "")
                local_orchestration = config.get_pi_config("architecture.local_orchestration", True)

            self.assertIn("小爱同学", str(wake_aliases))
            self.assertEqual(node_role, "light_frontend")
            self.assertFalse(local_orchestration)


if __name__ == "__main__":
    unittest.main()
