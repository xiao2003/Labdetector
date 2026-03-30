from __future__ import annotations

import unittest

from pc.desktop_app import (
    _classify_log_entry,
    _format_archive_record_label,
    _format_node_task_detail,
    _format_kb_import_feedback,
    _format_priority_event_card,
    _format_task_progress_line,
    _matches_log_filter,
    _present_hero_message,
    _present_orchestrator_status,
    _select_latest_priority_event,
)


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

    def test_orchestrator_status_is_presented_as_three_product_states(self) -> None:
        self.assertEqual(_present_orchestrator_status("ready"), "系统已可用")
        self.assertEqual(_present_orchestrator_status("downloading"), "后台准备中")
        self.assertEqual(_present_orchestrator_status("warming_up"), "后台准备中")
        self.assertEqual(_present_orchestrator_status("not_installed"), "后台准备中")
        self.assertEqual(_present_orchestrator_status("download_failed"), "后台准备失败（已回退规则链）")

    def test_hero_message_falls_back_to_product_state_for_waiting_config(self) -> None:
        self.assertEqual(_present_hero_message("等待配置", "downloading"), "后台准备中")
        self.assertEqual(_present_hero_message("", "ready"), "系统已可用")
        self.assertEqual(_present_hero_message("监控已启动", "ready"), "监控已启动")

    def test_priority_event_prefers_latest_warning(self) -> None:
        rows = [
            {"level": "INFO", "category": "运行状态", "summary": "普通事件"},
            {"level": "WARN", "category": "危化品专家", "summary": "检测到 HF 高危告警"},
        ]
        item = _select_latest_priority_event(rows)
        self.assertIsNotNone(item)
        title, detail = _format_priority_event_card(item)
        self.assertIn("高优先级事项", title)
        self.assertIn("HF", title)
        self.assertIn("HF", detail)

    def test_priority_event_empty_state_hides_secondary_hint(self) -> None:
        title, detail = _format_priority_event_card(None)
        self.assertEqual(title, "高优先级事项：当前无需要处理的事项")
        self.assertEqual(detail, "")

    def test_kb_import_feedback_uses_business_result_text(self) -> None:
        summary, dialog = _format_kb_import_feedback(
            {
                "scope": "expert.safety.chem_safety_expert",
                "imported_count": 3,
                "failed_count": 1,
                "structured_records": 2,
            }
        )
        self.assertIn("最近一次导入", summary)
        self.assertIn("作用域 expert.safety.chem_safety_expert", summary)
        self.assertIn("新增文档 3", summary)
        self.assertIn("新增文档数：3", dialog)

    def test_task_progress_line_formats_percent_and_detail(self) -> None:
        title, detail, percent, status = _format_task_progress_line(
            {
                "task_name": "节点自检",
                "detail": "正在安装缺失依赖",
                "percent": 48,
                "status": "running",
            },
            empty_title="空态标题",
            empty_detail="空态说明",
        )
        self.assertEqual(title, "节点自检")
        self.assertEqual(detail, "正在安装缺失依赖")
        self.assertEqual(percent, 48.0)
        self.assertEqual(status, "running")

    def test_node_task_detail_contains_node_identity_and_status(self) -> None:
        detail = _format_node_task_detail(
            "2",
            {
                "task_name": "节点 2 自检",
                "detail": "自动补全已完成，正在再次自检",
                "status": "running",
                "updated_at": "2026-03-29 21:00:00",
            },
        )
        self.assertIn("节点：2", detail)
        self.assertIn("状态：running", detail)
        self.assertIn("自动补全已完成", detail)

    def test_archive_record_label_prefers_opened_at(self) -> None:
        label = _format_archive_record_label(
            {
                "session_id": "20260330_101500_websocket_pi_cluster",
                "opened_at": "2026-03-30 10:15:00",
            }
        )
        self.assertEqual(label, "2026-03-30 10:15:00")


if __name__ == "__main__":
    unittest.main()
