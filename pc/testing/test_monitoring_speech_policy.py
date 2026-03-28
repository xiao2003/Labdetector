import unittest

from pc.core.monitoring_policy import should_speak_monitoring_result


class MonitoringSpeechPolicyTest(unittest.TestCase):
    def test_regular_ppe_reminder_should_not_auto_speak(self):
        self.assertFalse(
            should_speak_monitoring_result(
                "PPE穿戴检查",
                "PPE 规范提醒：检测到人员但未完整佩戴实验服、手套和护目镜。",
            )
        )

    def test_critical_hf_alert_should_auto_speak(self):
        self.assertTrue(
            should_speak_monitoring_result(
                "危化品识别",
                "极度危险：识别到 HF 且未检测到手套，请立即停止操作并上报。",
            )
        )


if __name__ == "__main__":
    unittest.main()
