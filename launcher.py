#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unified launcher for NeuroLab Hub desktop and workbench modes."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pc.app_identity import APP_NAME
from pc.tools.version_manager import get_app_version


APP_VERSION = get_app_version()


def run_cli_entry() -> int:
    from pc.webui.runtime import LabDetectorRuntime

    runtime = LabDetectorRuntime()
    print("=" * 56)
    print(f"{APP_NAME} v{APP_VERSION} CLI 模式")
    print("=" * 56)
    print("启动自检中...\n")
    for item in runtime.run_self_check():
        print(f"[{item['status'].upper()}] {item['title']}: {item['summary']}")
    print("\n切换到旧版控制台主流程。\n")

    from pc.main import main as cli_main

    try:
        cli_main()
        return 0
    except KeyboardInterrupt:
        print("\n[INFO] 已收到退出信号")
        return 0


def run_smoke_test(output_path: str) -> int:
    from pc.webui.runtime import LabDetectorRuntime

    runtime = LabDetectorRuntime()
    payload = runtime.bootstrap(include_self_check=False)
    runtime.shutdown()

    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=f"{APP_NAME} Launcher")
    parser.add_argument("--cli", action="store_true", help="使用旧版控制台入口")
    parser.add_argument("--web", action="store_true", help="使用浏览器控制台")
    parser.add_argument("--training-workbench", action="store_true", help="直接打开综合训练工作台")
    parser.add_argument("--llm-workbench", action="store_true", help="直接打开 LLM 微调工作台")
    parser.add_argument("--vision-workbench", action="store_true", help="直接打开识别模型训练工作台")
    parser.add_argument("--host", default="127.0.0.1", help="Web 控制台监听地址")
    parser.add_argument("--port", default=8765, type=int, help="Web 控制台监听端口")
    parser.add_argument("--open-browser", action="store_true", help="启动 Web 模式后自动打开浏览器")
    parser.add_argument("--smoke-test-file", default="", help="写出初始化 JSON 后退出，用于打包产物验收")
    return parser.parse_args(argv)


def _infer_mode_from_exe_name() -> str:
    exe_name = Path(sys.argv[0]).name.lower()
    if "llm" in exe_name:
        return "llm"
    if "vision" in exe_name or "detector" in exe_name:
        return "vision"
    if "training" in exe_name:
        return "training"
    return "default"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    inferred_mode = _infer_mode_from_exe_name()

    if args.smoke_test_file:
        return run_smoke_test(args.smoke_test_file)
    if args.cli:
        return run_cli_entry()
    if args.web:
        from pc.webui.server import serve_dashboard

        serve_dashboard(host=args.host, port=args.port, open_browser=args.open_browser)
        return 0

    if args.llm_workbench or inferred_mode == "llm":
        training_focus = "llm"
    elif args.vision_workbench or inferred_mode == "vision":
        training_focus = "vision"
    elif args.training_workbench or inferred_mode == "training":
        training_focus = "all"
    else:
        training_focus = ""

    from pc.desktop_app import launch_desktop_app

    return launch_desktop_app(
        open_training_workbench=bool(training_focus),
        training_focus=training_focus,
    )


if __name__ == "__main__":
    raise SystemExit(main())