from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List


PI_ROOT = Path(__file__).resolve().parents[1]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="执行仿真树莓派启动环境测试")
    parser.add_argument(
        "--report-file",
        default=str(Path("D:/NeuroLab/_machine_switch_test/pi_simulated_startup_env_report.json")),
        help="测试报告输出路径",
    )
    return parser.parse_args()


def _copy_pi_tree(target_root: Path) -> Path:
    copied_root = target_root / "pi"
    shutil.copytree(
        PI_ROOT,
        copied_root,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
    )
    return copied_root


def _load_module(module_name: str, module_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载模块: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_simulated_startup_env_test(report_file: str) -> Dict[str, Any]:
    report_path = Path(report_file).resolve()
    report: Dict[str, Any] = {
        "success": False,
        "report_file": str(report_path),
        "copied_root": "",
        "steps": [],
        "checks": {},
        "errors": [],
    }

    def add_step(name: str, **payload: Any) -> None:
        row = {"name": name}
        row.update(payload)
        report["steps"].append(row)

    workspace = tempfile.mkdtemp(prefix="neurolab_pi_sim_", dir=str(report_path.parent))
    copied_root = _copy_pi_tree(Path(workspace))
    report["copied_root"] = str(copied_root)

    try:
        shell_path = copied_root / "start_pi_node.sh"
        bootstrap_path = copied_root / "bootstrap_entry.py"
        config_path = copied_root / "config.ini"
        runtime_state_dir = copied_root / "runtime_state"
        runtime_state_dir.mkdir(parents=True, exist_ok=True)
        (runtime_state_dir / "install_state.json").write_text(
            json.dumps({"status": "success"}, ensure_ascii=False),
            encoding="utf-8",
        )
        if str(copied_root) not in sys.path:
            sys.path.insert(0, str(copied_root))

        shell_text = shell_path.read_text(encoding="utf-8")
        report["checks"]["shell_uses_project_venv"] = '".venv"' in shell_text or "/.venv" in shell_text
        report["checks"]["shell_targets_bootstrap"] = "bootstrap_entry.py" in shell_text
        add_step(
            "shell_checked",
            shell_uses_project_venv=report["checks"]["shell_uses_project_venv"],
            shell_targets_bootstrap=report["checks"]["shell_targets_bootstrap"],
        )

        bootstrap = _load_module("pi_bootstrap_simulated", bootstrap_path)
        launched_args: List[List[str]] = []
        scheduled_installs: List[bool] = []

        bootstrap._runtime_ready = lambda: True
        bootstrap._maybe_schedule_runtime_install = lambda: scheduled_installs.append(True) or 0
        bootstrap._launch_main = lambda args: launched_args.append(list(args)) or 0

        default_exit = int(bootstrap.main([]))
        status_exit = int(bootstrap.main(["status"]))

        report["checks"]["bootstrap_default_exit"] = default_exit
        report["checks"]["bootstrap_status_exit"] = status_exit
        report["checks"]["default_launch_args"] = launched_args[0] if launched_args else []
        report["checks"]["status_launch_args"] = launched_args[1] if len(launched_args) > 1 else []
        report["checks"]["scheduled_installs"] = scheduled_installs
        add_step(
            "bootstrap_checked",
            default_launch_args=report["checks"]["default_launch_args"],
            status_launch_args=report["checks"]["status_launch_args"],
            scheduled_install_rounds=len(scheduled_installs),
        )

        bootstrap._runtime_ready = lambda: False
        scheduled_exit = int(bootstrap.main(["start"]))
        report["checks"]["scheduled_exit"] = scheduled_exit
        add_step("runtime_schedule_checked", scheduled_exit=scheduled_exit, scheduled_install_rounds=len(scheduled_installs))

        config_text = config_path.read_text(encoding="utf-8-sig")
        report["checks"]["config_uses_relative_detector_weights"] = "weights_path = yolov8n.pt" in config_text
        add_step(
            "config_checked",
            config_uses_relative_detector_weights=report["checks"]["config_uses_relative_detector_weights"],
        )

        if report["checks"]["default_launch_args"] != ["start"]:
            raise AssertionError(f"默认启动参数不正确: {report['checks']['default_launch_args']}")
        if report["checks"]["status_launch_args"] != ["status"]:
            raise AssertionError(f"显式命令透传不正确: {report['checks']['status_launch_args']}")
        if scheduled_installs != [True]:
            raise AssertionError(f"安装调度行为不正确: {scheduled_installs}")
        if not report["checks"]["shell_uses_project_venv"]:
            raise AssertionError("启动脚本未固定使用项目本地 .venv")
        if not report["checks"]["shell_targets_bootstrap"]:
            raise AssertionError("启动脚本未切换到 bootstrap_entry.py")
        if not report["checks"]["config_uses_relative_detector_weights"]:
            raise AssertionError("交付配置中的检测权重仍不是可迁移的相对路径")
        if scheduled_exit != 0:
            raise AssertionError(f"缺失运行时时启动不应报错退出: {scheduled_exit}")

        report["success"] = True
        return report
    except Exception as exc:
        report["errors"].append(str(exc))
        return report
    finally:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    args = _parse_args()
    report = run_simulated_startup_env_test(args.report_file)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
