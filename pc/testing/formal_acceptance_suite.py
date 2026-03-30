from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import zipfile
from pathlib import Path
from typing import Any, Dict, List


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RELEASE_ROOT = PROJECT_ROOT / "release"

STRUCTURE_TESTS = [
    "pc.testing.test_orchestrator_runtime",
    "pc.testing.test_orchestrator_model",
    "pc.testing.test_remote_voice_routing",
    "pc.testing.test_expert_manager_voice_routing",
    "pc.testing.test_expert_capability_facts",
    "pc.testing.test_monitoring_speech_policy",
    "pc.testing.test_gui_knowledge_dispatch",
    "pc.testing.test_ollama_model_catalog",
    "pc.testing.test_desktop_log_filters",
]

PI_TESTS = [
    "pi.testing.test_pi_config",
    "pi.testing.test_pi_self_check_progress",
    "pi.testing.test_voice_interaction",
    "pi.testing.test_runtime_installer",
    "pi.testing.test_audio_replay",
    "pi.testing.test_model_downloader_offline",
]

MANUAL_REVIEW_ITEMS = [
    "主界面默认窗口尺寸下文字完整可见",
    "左侧 4 个主操作入口保持 2x2 排布",
    "首屏状态只出现三态产品文案",
    "高优先级事项卡片空态和高危态都可读",
    "任务进度以单行进度条形式进入日志流，文案清晰",
    "节点状态区不显示额外进度卡片，也不会挤压主界面",
    "系统事件列表无第二行额外说明小字",
    "节点状态区为卡片样式而不是多张小日志表",
    "知识中心文字无遮挡、按钮不重叠",
    "专家中心文字无遮挡、按钮不重叠",
    "训练中心文字无遮挡、按钮不重叠",
    "档案中心文字无遮挡、按钮不重叠",
    "云端配置文字无遮挡、按钮不重叠",
    "About 只打开一个窗口",
    "Ollama 候选可见 qwen3.5:4b / 9b / 27b / 35b",
]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="执行 NeuroLab Hub 全层正式验收总控链。")
    parser.add_argument(
        "--installer",
        default=str(RELEASE_ROOT / "NeuroLab-Hub-Setup-v1.0.0.exe"),
        help="正式安装包路径。",
    )
    parser.add_argument(
        "--install-dir",
        default=str(RELEASE_ROOT / "formal_acceptance_install"),
        help="安装目标目录。",
    )
    parser.add_argument(
        "--report-dir",
        default=str(RELEASE_ROOT / f"formal_acceptance_{time.strftime('%Y%m%d_%H%M%S')}"),
        help="总控验收报告输出目录。",
    )
    parser.add_argument(
        "--manual-review-file",
        default="",
        help="人工 GUI 观感验收记录 Markdown 路径；为空时自动生成模板。",
    )
    parser.add_argument(
        "--installer-smoke-report",
        default="",
        help="已存在的管理员态安装首启 smoke 报告路径；提供后不再在总控链内部重复执行。",
    )
    parser.add_argument(
        "--allow-manual-pending",
        action="store_true",
        help="允许人工验收尚未完成时继续生成汇总报告。",
    )
    parser.add_argument(
        "--skip-installer-smoke",
        action="store_true",
        help="跳过管理员安装首启 smoke，仅用于本地验证总控脚本。",
    )
    parser.add_argument(
        "--node-count",
        type=int,
        default=1,
        help="虚拟 Pi 节点数量，仅支持 1 或 4。",
    )
    return parser.parse_args()


def _run_command(command: List[str], *, cwd: Path) -> dict[str, Any]:
    started_at = time.strftime("%Y-%m-%d %H:%M:%S")
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    completed = subprocess.run(
        command,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    return {
        "command": command,
        "cwd": str(cwd),
        "started_at": started_at,
        "finished_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "returncode": int(completed.returncode),
        "stdout": str(completed.stdout or ""),
        "stderr": str(completed.stderr or ""),
        "ok": completed.returncode == 0,
    }


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_manual_review_template(path: Path) -> None:
    lines = [
        "# NeuroLab Hub GUI 人工观感验收记录",
        "",
        "> 请在安装后的真实程序中逐项核对，通过则把 `[ ]` 改成 `[x]`。",
        "",
        "## 观感检查项",
        "",
    ]
    for item in MANUAL_REVIEW_ITEMS:
        lines.append(f"- [ ] {item}")
    lines.extend(
        [
            "",
            "## 截图记录",
            "",
            "- [ ] 主界面",
            "- [ ] 知识中心",
            "- [ ] 专家中心",
            "- [ ] 训练中心",
            "- [ ] 档案中心",
            "- [ ] 云端配置",
            "- [ ] About 窗口",
            "",
            "## 需修复项",
            "",
            "- 无",
            "",
            "## 结论",
            "",
            "- [ ] 人工 GUI 观感验收通过",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _parse_manual_review(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "exists": False,
            "completed": False,
            "passed": False,
            "unchecked_items": MANUAL_REVIEW_ITEMS,
        }
    text = path.read_text(encoding="utf-8")
    unchecked_items: List[str] = []
    for item in MANUAL_REVIEW_ITEMS:
        if f"- [x] {item}" in text:
            continue
        unchecked_items.append(item)
    passed = "- [x] 人工 GUI 观感验收通过" in text and not unchecked_items
    return {
        "exists": True,
        "completed": not unchecked_items,
        "passed": passed,
        "unchecked_items": unchecked_items,
    }


def _layer_status(*flags: bool) -> str:
    return "passed" if all(flags) else "failed"


def _build_summary_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# NeuroLab Hub 正式验收总控链结果",
        "",
        f"- 开始时间：{report.get('started_at', '')}",
        f"- 结束时间：{report.get('finished_at', '')}",
        f"- 总结论：{'通过' if report.get('success') else '未通过'}",
        "",
        "## 分层结果",
        "",
    ]
    for layer, payload in report.get("layers", {}).items():
        lines.append(f"- {layer}：{payload.get('status', 'unknown')}")
    lines.extend(
        [
            "",
            "## 关键报告",
            "",
        ]
    )
    for item in report.get("artifacts", []):
        lines.append(f"- {item}")
    lines.extend(
        [
            "",
            "## 失败项",
            "",
        ]
    )
    failures = report.get("failures", [])
    if failures:
        lines.extend(f"- {item}" for item in failures)
    else:
        lines.append("- 无")
    return "\n".join(lines) + "\n"


def _zip_artifacts(zip_path: Path, files: List[Path]) -> None:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_path in files:
            if not file_path.exists() or not file_path.is_file():
                continue
            zf.write(file_path, arcname=file_path.name)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = _parse_args()
    report_dir = Path(args.report_dir).resolve()
    report_dir.mkdir(parents=True, exist_ok=True)
    installer_path = Path(args.installer).resolve()
    install_dir = Path(args.install_dir).resolve()
    manual_review_path = Path(args.manual_review_file).resolve() if args.manual_review_file else report_dir / "manual_gui_review_checklist.md"
    if not manual_review_path.exists():
        _write_manual_review_template(manual_review_path)

    python_exe = Path(sys.executable).resolve()
    report: dict[str, Any] = {
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "python": str(python_exe),
        "installer": str(installer_path),
        "install_dir": str(install_dir),
        "report_dir": str(report_dir),
        "steps": {},
        "layers": {},
        "artifacts": [],
        "failures": [],
    }

    structure_result = _run_command(
        [str(python_exe), "-m", "unittest", *STRUCTURE_TESTS, *PI_TESTS],
        cwd=PROJECT_ROOT,
    )
    report["steps"]["structure_and_pi"] = structure_result

    gui_release_report = report_dir / "gui_release_acceptance_report.json"
    gui_release_result = _run_command(
        [
            str(python_exe),
            "-m",
            "pc.testing.gui_release_acceptance_test",
            "--report-file",
            str(gui_release_report),
            "--node-count",
            str(args.node_count),
        ],
        cwd=PROJECT_ROOT,
    )
    report["steps"]["gui_release_acceptance"] = gui_release_result
    gui_release_payload = _load_json(gui_release_report)

    gui_full_report = report_dir / "gui_full_closed_loop_report.json"
    gui_full_result = _run_command(
        [
            str(python_exe),
            "-m",
            "pc.testing.gui_full_closed_loop_test",
            "--report-file",
            str(gui_full_report),
        ],
        cwd=PROJECT_ROOT,
    )
    report["steps"]["gui_full_closed_loop"] = gui_full_result
    gui_full_payload = _load_json(gui_full_report)

    voice_report = report_dir / "virtual_text_voice_closed_loop_report.json"
    voice_result = _run_command(
        [
            str(python_exe),
            "-m",
            "pc.testing.virtual_text_voice_closed_loop_test",
            "--report-file",
            str(voice_report),
        ],
        cwd=PROJECT_ROOT,
    )
    report["steps"]["pc_pi_closed_loop"] = voice_result
    voice_payload = _load_json(voice_report)

    smoke_payload: dict[str, Any] = {}
    provided_smoke_report = Path(args.installer_smoke_report).resolve() if args.installer_smoke_report else None
    if provided_smoke_report and provided_smoke_report.exists():
        smoke_payload = _load_json(provided_smoke_report)
        report["steps"]["installer_smoke"] = {
            "ok": bool(smoke_payload),
            "reused_report": str(provided_smoke_report),
        }
    elif args.skip_installer_smoke:
        report["steps"]["installer_smoke"] = {
            "ok": False,
            "skipped": True,
            "reason": "skip_installer_smoke",
        }
    else:
        smoke_report = report_dir / "installer_first_launch_smoke_report.json"
        smoke_result = _run_command(
            [
                str(python_exe),
                "-m",
                "pc.testing.installer_first_launch_smoke",
                "--installer",
                str(installer_path),
                "--install-dir",
                str(install_dir),
                "--report",
                str(smoke_report),
                "--clear-runtime-state",
            ],
            cwd=PROJECT_ROOT,
        )
        report["steps"]["installer_smoke"] = smoke_result
        smoke_payload = _load_json(smoke_report)

    manual_review = _parse_manual_review(manual_review_path)
    report["steps"]["manual_review"] = manual_review

    layers = {
        "交互与展示层": _layer_status(bool(gui_release_payload.get("success")), bool(gui_full_payload.get("success")), bool(manual_review.get("passed", False) or args.allow_manual_pending)),
        "会话与运行时层": _layer_status(bool(structure_result.get("ok")), bool(gui_release_payload.get("success")), bool(smoke_payload.get("process_started", False) or args.skip_installer_smoke)),
        "管家编排层": _layer_status(bool(structure_result.get("ok")), bool(voice_payload.get("success"))),
        "执行与知识层": _layer_status(bool(structure_result.get("ok")), bool(gui_release_payload.get("success")), bool(gui_full_payload.get("success"))),
        "通信与节点管理层": _layer_status(bool(voice_payload.get("success")), bool(gui_full_payload.get("success"))),
        "Pi 轻前端边缘层": _layer_status(bool(structure_result.get("ok")), bool(voice_payload.get("success"))),
    }
    report["layers"] = {key: {"status": value} for key, value in layers.items()}

    if not structure_result.get("ok"):
        report["failures"].append("结构与 Pi 边缘回归未通过。")
    if not gui_release_payload.get("success"):
        report["failures"].append("GUI 发布验收未通过。")
    if not gui_full_payload.get("success"):
        report["failures"].append("GUI 全闭环未通过。")
    if not voice_payload.get("success"):
        report["failures"].append("PC-Pi 语音/视频闭环未通过。")
    if not args.skip_installer_smoke and not smoke_payload.get("install_ok", False):
        report["failures"].append("安装包首启 smoke 未通过。")
    if not manual_review.get("passed", False):
        if args.allow_manual_pending:
            report["failures"].append("人工 GUI 观感验收待补录。")
        else:
            report["failures"].append("人工 GUI 观感验收未完成。")

    report["artifacts"] = [
        str(path)
        for path in [
            gui_release_report,
            gui_full_report,
            voice_report,
            provided_smoke_report if provided_smoke_report else Path(),
            report_dir / "installer_first_launch_smoke_report.json",
            manual_review_path,
        ]
        if path.exists()
    ]
    report["success"] = not any(
        [
            not structure_result.get("ok"),
            not gui_release_payload.get("success"),
            not gui_full_payload.get("success"),
            not voice_payload.get("success"),
            (not args.skip_installer_smoke and not smoke_payload.get("install_ok", False)),
            (not args.allow_manual_pending and not manual_review.get("passed", False)),
        ]
    )
    report["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")

    summary_path = report_dir / "fresh_validation_summary_1.0.0.md"
    summary_text = _build_summary_markdown(report)
    summary_path.write_text(summary_text, encoding="utf-8")
    report["artifacts"].append(str(summary_path))

    report_path = report_dir / "formal_acceptance_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report["artifacts"].append(str(report_path))

    fresh_validation_zip = report_dir / "NeuroLab_Hub_1.0.0_fresh_validation.zip"
    _zip_artifacts(
        fresh_validation_zip,
        [
            gui_release_report,
            gui_full_report,
            voice_report,
            report_dir / "installer_first_launch_smoke_report.json",
            manual_review_path,
            summary_path,
            report_path,
        ],
    )
    report["artifacts"].append(str(fresh_validation_zip))
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
