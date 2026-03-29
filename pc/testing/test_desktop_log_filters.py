from __future__ import annotations

import unittest

from pc.desktop_app import _classify_log_entry, _matches_log_filter


class DesktopLogFilterTests(unittest.TestCase):
    def test_autonomy_log_is_classified_as_dispatch(self) -> None:
        category, summary = _classify_log_entry("[AUTONOMY] 管家已执行动作: open_training_center | intent='open_training_center'", "INFO", "[autonomy] 管家已执行动作")
        self.assertEqual(category, "自治调度")
        self.assertIn("管家已执行动作", summary)

    def test_warning_filter_only_keeps_alert_levels(self) -> None:
        warn_row = {"level": "WARN", "category": "运行状态"}
        info_row = {"level": "INFO", "category": "运行状态"}
        self.assertTrue(_matches_log_filter(warn_row, "告警"))
        self.assertFalse(_matches_log_filter(info_row, "告警"))

    def test_dispatch_filter_matches_autonomy_and_voice(self) -> None:
        autonomy_row = {"level": "INFO", "category": "自治调度"}
        voice_row = {"level": "INFO", "category": "语音交互"}
        system_row = {"level": "INFO", "category": "训练"}
        self.assertTrue(_matches_log_filter(autonomy_row, "调度"))
        self.assertTrue(_matches_log_filter(voice_row, "调度"))
        self.assertFalse(_matches_log_filter(system_row, "调度"))


if __name__ == "__main__":
    unittest.main()
