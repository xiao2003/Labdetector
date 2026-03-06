#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unified launcher for LabDetector desktop/web/cli modes."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pcside.app_identity import APP_DISPLAY_NAME, APP_NAME, COMPANY_NAME
from pcside.desktop_app import launch_desktop_app
from pcside.tools.version_manager import get_app_version
from pcside.webui.runtime import LabDetectorRuntime
from pcside.webui.server import serve_dashboard


APP_VERSION = get_app_version()


def run_cli_entry() -> int:
    runtime = LabDetectorRuntime()
    print("=" * 56)
    print(f"{APP_NAME} v{APP_VERSION} CLI 模式")
    print("=" * 56)
    print("启动自检中...\n")
    for item in runtime.run_self_check():
        print(f"[{item['status'].upper()}] {item['title']}: {item['summary']}")
    print("\n切换到旧版控制台主流程。\n")

    from pcside.main import main as cli_main

    try:
        cli_main()
        return 0
    except KeyboardInterrupt:
        print("\n[INFO] 已收到退出信号")
        return 0


def run_smoke_test(output_path: str) -> int:
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
    parser.add_argument("--host", default="127.0.0.1", help="Web 控制台监听地址")
    parser.add_argument("--port", default=8765, type=int, help="Web 控制台监听端口")
    parser.add_argument("--open-browser", action="store_true", help="启动 Web 模式后自动打开浏览器")
    parser.add_argument("--smoke-test-file", default="", help="写出初始化 JSON 后退出，用于打包产物验收")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    if args.smoke_test_file:
        return run_smoke_test(args.smoke_test_file)
    if args.cli:
        return run_cli_entry()
    if args.web:
        print("=" * 56)
        print(f"{APP_NAME} v{APP_VERSION} Web 控制台")
        print("=" * 56)
        print(f"访问地址: http://{args.host}:{args.port}\n")
        serve_dashboard(host=args.host, port=args.port, open_browser=args.open_browser)
        return 0

    print("=" * 56)
    print(f"{APP_DISPLAY_NAME} v{APP_VERSION}")
    print(COMPANY_NAME)
    print("=" * 56)
    print("正在启动桌面可视化软件...\n")
    return launch_desktop_app()


if __name__ == "__main__":
    raise SystemExit(main())
