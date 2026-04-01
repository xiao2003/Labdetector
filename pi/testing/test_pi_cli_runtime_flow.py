from __future__ import annotations

import types
import unittest
from unittest.mock import patch

from pi import pi_cli


class PiCliRuntimeFlowTests(unittest.TestCase):
    def test_start_node_runs_self_check_before_runtime_main(self) -> None:
        calls: list[tuple[str, object]] = []
        runtime = types.SimpleNamespace(
            run_pi_self_check=lambda auto_install=None: calls.append(("self_check", auto_install)) or True,
            main=lambda: calls.append(("main", None)),
        )

        snapshot = {
            "local_ip": "127.0.0.1",
            "network": {"pc_ip": "127.0.0.1", "ws_port": "8001"},
            "detector": {"weights_path": "yolov8n.pt"},
        }

        with patch("pi.pi_cli.is_install_completed", return_value=True), \
             patch("pi.pi_cli._load_runtime", return_value=runtime), \
             patch("pi.pi_cli._config_snapshot", return_value=snapshot), \
             patch("pi.pi_cli.get_pi_config", side_effect=lambda key, default=None: True if key == "self_check.auto_install_dependencies" else default), \
             patch("builtins.print"):
            exit_code = pi_cli.start_node(skip_self_check=False, auto_install_deps=None)

        self.assertEqual(exit_code, 0)
        self.assertEqual(calls, [("self_check", True), ("main", None)])

    def test_run_self_check_uses_config_default_and_returns_failure_code(self) -> None:
        calls: list[object] = []
        runtime = types.SimpleNamespace(
            run_pi_self_check=lambda auto_install=None: calls.append(auto_install) or False,
        )

        with patch("pi.pi_cli.is_install_completed", return_value=True), \
             patch("pi.pi_cli._load_runtime", return_value=runtime), \
             patch("pi.pi_cli.get_pi_config", side_effect=lambda key, default=None: False if key == "self_check.auto_install_dependencies" else default):
            exit_code = pi_cli.run_self_check(auto_install_deps=None)

        self.assertEqual(exit_code, 2)
        self.assertEqual(calls, [False])


if __name__ == "__main__":
    unittest.main()
