from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pi.tools import runtime_installer


class RuntimeInstallerTest(unittest.TestCase):
    def test_build_status_payload_contains_paths(self) -> None:
        with tempfile.TemporaryDirectory(prefix="neurolab_runtime_state_") as temp_dir:
            state_dir = Path(temp_dir)
            state_path = state_dir / "install_state.json"
            pid_path = state_dir / "install.pid"
            log_path = state_dir / "install.log"
            state_path.write_text(json.dumps({"status": "running", "stage": "pip"}, ensure_ascii=False), encoding="utf-8")
            pid_path.write_text("999999", encoding="utf-8")
            log_path.write_text("", encoding="utf-8")

            with mock.patch.object(runtime_installer, "RUNTIME_STATE_DIR", state_dir), \
                 mock.patch.object(runtime_installer, "INSTALL_STATE_PATH", state_path), \
                 mock.patch.object(runtime_installer, "INSTALL_PID_PATH", pid_path), \
                 mock.patch.object(runtime_installer, "INSTALL_LOG_PATH", log_path), \
                 mock.patch.object(runtime_installer, "_pid_alive", return_value=False):
                payload = runtime_installer.build_status_payload()

            self.assertEqual(payload["status"], "running")
            self.assertEqual(payload["stage"], "pip")
            self.assertFalse(payload["running"])
            self.assertEqual(payload["state_path"], str(state_path))
            self.assertEqual(payload["log_path"], str(log_path))


if __name__ == "__main__":
    unittest.main()
