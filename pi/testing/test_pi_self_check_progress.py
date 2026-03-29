from __future__ import annotations

import unittest

from pi import pisend_receive


class PiSelfCheckProgressTests(unittest.TestCase):
    def test_self_check_emits_progress_stages(self) -> None:
        rows = []

        previous_find = pisend_receive._find_missing_pi_dependencies
        previous_install = pisend_receive._install_pi_dependencies
        previous_detect = pisend_receive.detect_audio_capabilities
        previous_loader = pisend_receive._load_runtime_modules
        previous_vosk = pisend_receive.check_and_download_vosk
        previous_picamera = pisend_receive.PICAMERA_AVAILABLE
        try:
            call_counter = {"count": 0}

            def _fake_find(_mapping):
                call_counter["count"] += 1
                return ["vosk"] if call_counter["count"] <= 2 else []

            pisend_receive._find_missing_pi_dependencies = _fake_find
            pisend_receive._install_pi_dependencies = lambda missing: (list(missing), [], ["安装成功: vosk"])
            pisend_receive.detect_audio_capabilities = lambda: (True, True)
            pisend_receive._load_runtime_modules = lambda: None
            pisend_receive.check_and_download_vosk = lambda _target: True
            pisend_receive.PICAMERA_AVAILABLE = True

            ok = pisend_receive.run_pi_self_check(auto_install=True, progress_callback=rows.append)
        finally:
            pisend_receive._find_missing_pi_dependencies = previous_find
            pisend_receive._install_pi_dependencies = previous_install
            pisend_receive.detect_audio_capabilities = previous_detect
            pisend_receive._load_runtime_modules = previous_loader
            pisend_receive.check_and_download_vosk = previous_vosk
            pisend_receive.PICAMERA_AVAILABLE = previous_picamera

        self.assertTrue(ok)
        stages = [str(row.get("stage")) for row in rows]
        self.assertEqual(stages, ["scan", "repair", "recheck", "done"])
        self.assertEqual(rows[-1]["status"], "success")
        self.assertIn("vosk", rows[-1]["installed"])


if __name__ == "__main__":
    unittest.main()
