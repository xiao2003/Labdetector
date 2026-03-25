from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pc.tools.pi_one_click_setup import PiOneClickSetup


class PiOneClickSetupTest(unittest.TestCase):
    def _config_path(self) -> Path:
        temp_dir = tempfile.TemporaryDirectory(prefix="neurolab_pi_setup_")
        self.addCleanup(temp_dir.cleanup)
        path = Path(temp_dir.name) / "config.json"
        path.write_text(
            json.dumps(
                {
                    "preferred_host": "192.168.1.185",
                    "candidate_hosts": ["raspberrypi.local"],
                    "ssh": {
                        "user": "alexander",
                        "password": "xiao2003",
                        "hostkey": "ssh-ed25519 255 SHA256:test",
                    },
                    "wifi": {
                        "ssid": "12345201-5G",
                        "password": "12345201",
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return path

    def test_current_wifi_ssid_parsing(self) -> None:
        runner = PiOneClickSetup(self._config_path())
        with patch.object(runner, "_run") as mocked_run:
            mocked_run.return_value.stdout = "\n    SSID                   : 12345201-5G\n    BSSID                  : aa\n"
            mocked_run.return_value.returncode = 0
            self.assertEqual(runner._current_wifi_ssid(), "12345201-5G")

    def test_candidate_hosts_include_arp_entries(self) -> None:
        runner = PiOneClickSetup(self._config_path())
        with patch.object(runner, "_run") as mocked_run:
            mocked_run.return_value.stdout = "  192.168.1.185          aa-bb-cc-dd-ee-ff     dynamic\n"
            mocked_run.return_value.returncode = 0
            hosts = runner._candidate_hosts()
        self.assertIn("192.168.1.185", hosts)
        self.assertIn("raspberrypi.local", hosts)

    def test_wifi_credentials_can_fallback_to_windows_profile(self) -> None:
        runner = PiOneClickSetup(self._config_path())
        with patch.object(runner, "_current_wifi_ssid", return_value="12345201-5G"), \
             patch.object(runner, "_current_wifi_password", return_value="12345201"):
            ssid, password = runner._resolve_wifi_credentials()
        self.assertEqual(ssid, "12345201-5G")
        self.assertEqual(password, "12345201")


if __name__ == "__main__":
    unittest.main()
