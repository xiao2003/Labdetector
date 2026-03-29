# -*- coding: utf-8 -*-
"""安装包首启 smoke 脚本测试。"""

from __future__ import annotations

import unittest

from pc.testing.installer_first_launch_smoke import _classify_install_result


class InstallerFirstLaunchSmokeTest(unittest.TestCase):
    """验证安装结果分类逻辑。"""

    def test_non_admin_no_log_is_reported_as_blocked(self) -> None:
        result = _classify_install_result(
            install_exit_code=1,
            exe_exists=False,
            installer_log_exists=False,
            is_admin=False,
        )
        self.assertTrue(result["blocked"])
        self.assertEqual(result["blocked_reason"], "installer_requires_admin")

    def test_real_install_success_is_not_blocked(self) -> None:
        result = _classify_install_result(
            install_exit_code=0,
            exe_exists=True,
            installer_log_exists=True,
            is_admin=False,
        )
        self.assertFalse(result["blocked"])
        self.assertEqual(result["blocked_reason"], "")

    def test_admin_failure_is_not_rewritten_as_permission_issue(self) -> None:
        result = _classify_install_result(
            install_exit_code=1,
            exe_exists=False,
            installer_log_exists=False,
            is_admin=True,
        )
        self.assertFalse(result["blocked"])
        self.assertEqual(result["blocked_reason"], "")


if __name__ == "__main__":
    unittest.main()
