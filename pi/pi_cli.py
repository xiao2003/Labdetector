#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""NeuroLab Hub Raspberry Pi CLI entrypoint."""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

try:
    from .config import get_pi_config, get_pi_path_config, set_pi_config
    from .tools.runtime_installer import (
        build_status_payload,
        is_install_completed,
        read_install_log_tail,
        run_install,
        trigger_background_install,
    )
    from .tools.version_manager import get_app_version
except ImportError:
    from config import get_pi_config, get_pi_path_config, set_pi_config
    from tools.runtime_installer import (
        build_status_payload,
        is_install_completed,
        read_install_log_tail,
        run_install,
        trigger_background_install,
    )
    from tools.version_manager import get_app_version

APP_VERSION = get_app_version()
CONFIG_PATH = Path(__file__).resolve().with_name("config.ini")
VENV_PYTHON = Path(__file__).resolve().with_name(".venv") / "bin" / "python3"
VENV_REEXEC_ENV = "NEUROLAB_PI_VENV_REEXEC"


def _local_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return str(sock.getsockname()[0])
    except OSError:
        return "127.0.0.1"


def _bool_text(value: Any) -> str:
    return "开启" if bool(value) else "关闭"


def _parse_bool(value: str) -> bool:
    lowered = value.strip().lower()
    if lowered in {"1", "true", "yes", "on", "y"}:
        return True
    if lowered in {"0", "false", "no", "off", "n"}:
        return False
    raise argparse.ArgumentTypeError("布尔值只支持 true/false、yes/no、1/0")


def _config_snapshot() -> dict[str, Any]:
    return {
        "version": APP_VERSION,
        "config_path": str(CONFIG_PATH),
        "local_ip": _local_ip(),
        "network": {
            "pc_ip": get_pi_config("network.pc_ip", "") or "",
            "ws_port": str(get_pi_config("network.ws_port", "8001") or "8001"),
        },
        "voice": {
            "wake_word": str(get_pi_config("voice.wake_word", "小爱同学") or "小爱同学"),
            "online_recognition": bool(get_pi_config("voice.online_recognition", True)),
            "model_path": str(get_pi_config("voice.model_path", "voice/model") or "voice/model"),
            "resolved_model_path": get_pi_path_config("voice.model_path", "voice/model"),
        },
        "detector": {
            "weights_path": str(get_pi_config("detector.weights_path", "yolov8n.pt") or "yolov8n.pt"),
            "conf": float(get_pi_config("detector.conf", 0.4) or 0.4),
            "imgsz": int(get_pi_config("detector.imgsz", 640) or 640),
        },
    }


def _should_reexec_into_venv() -> bool:
    """统一把直接调用的 pi_cli 收敛到项目虚拟环境，避免系统 Python 与项目环境分叉。"""
    if os.environ.get(VENV_REEXEC_ENV) == "1":
        return False
    if not VENV_PYTHON.exists():
        return False
    try:
        return VENV_PYTHON.resolve() != Path(sys.executable).resolve()
    except OSError:
        return True


def _reexec_into_venv(argv: list[str]) -> int:
    env = os.environ.copy()
    env[VENV_REEXEC_ENV] = "1"
    process = subprocess.run([str(VENV_PYTHON), str(Path(__file__).resolve()), *argv], env=env)
    return int(process.returncode)


def _print_block(data: dict[str, Any]) -> None:
    print(f"NeuroLab Hub Pi CLI v{data['version']}")
    print(f"配置文件: {data['config_path']}")
    print(f"本机地址: {data['local_ip']}")
    print(f"中枢地址: {data['network']['pc_ip'] or '未设置'}")
    print(f"WebSocket 端口: {data['network']['ws_port']}")
    print(f"唤醒词: {data['voice']['wake_word']}")
    print(f"在线语音识别: {_bool_text(data['voice']['online_recognition'])}")
    print(f"离线模型目录: {data['voice']['model_path']}")
    print(f"离线模型绝对目录: {data['voice']['resolved_model_path']}")
    print(f"检测权重: {data['detector']['weights_path']}")
    print(f"检测阈值: {data['detector']['conf']}")
    print(f"检测尺寸: {data['detector']['imgsz']}")


def _load_runtime():
    try:
        from . import pisend_receive as runtime
    except ImportError:
        import pisend_receive as runtime

    return runtime


def show_status(as_json: bool = False) -> int:
    snapshot = _config_snapshot()
    if as_json:
        print(json.dumps(snapshot, ensure_ascii=False, indent=2))
    else:
        _print_block(snapshot)
    return 0


def show_config(as_json: bool = False) -> int:
    return show_status(as_json=as_json)


def set_config_value(key: str, value: Any) -> int:
    set_pi_config(key, value)
    print(f"已更新 {key} = {value}")
    return 0


def apply_start_overrides(args: argparse.Namespace) -> None:
    if getattr(args, "pc_ip", None):
        set_pi_config("network.pc_ip", args.pc_ip)
    if getattr(args, "ws_port", None):
        set_pi_config("network.ws_port", args.ws_port)
    if getattr(args, "wake_word", None):
        set_pi_config("voice.wake_word", args.wake_word)
    if getattr(args, "online_recognition", None) is not None:
        set_pi_config("voice.online_recognition", args.online_recognition)
    if getattr(args, "weights_path", None):
        set_pi_config("detector.weights_path", args.weights_path)
    if getattr(args, "detector_conf", None) is not None:
        set_pi_config("detector.conf", args.detector_conf)
    if getattr(args, "detector_imgsz", None) is not None:
        set_pi_config("detector.imgsz", args.detector_imgsz)


def start_node(skip_self_check: bool = False, auto_install_deps: Optional[bool] = None) -> int:
    if not is_install_completed():
        payload = build_status_payload()
        print("Pi 运行时尚未安装完成，请先查看安装状态。")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 3

    runtime = _load_runtime()
    snapshot = _config_snapshot()
    print("准备启动 NeuroLab Hub 树莓派边缘端")
    print(f"本机地址: {snapshot['local_ip']}")
    print(f"中枢地址: {snapshot['network']['pc_ip'] or '未设置，等待自动发现'}")
    print(f"端口: {snapshot['network']['ws_port']}")
    print(f"检测权重: {snapshot['detector']['weights_path']}")
    if auto_install_deps is None:
        auto_install_deps = bool(get_pi_config("self_check.auto_install_dependencies", True))
    if not skip_self_check:
        ok = runtime.run_pi_self_check(auto_install=auto_install_deps)
        if not ok:
            return 2
    runtime.main()
    return 0


def run_self_check(auto_install_deps: Optional[bool] = None) -> int:
    if not is_install_completed():
        payload = build_status_payload()
        print("Pi 运行时尚未安装完成，当前仅支持查看安装状态。")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 3
    runtime = _load_runtime()
    if auto_install_deps is None:
        auto_install_deps = bool(get_pi_config("self_check.auto_install_dependencies", True))
    ok = runtime.run_pi_self_check(auto_install=auto_install_deps)
    return 0 if ok else 2


def install_runtime(background: bool = False, force: bool = False) -> int:
    if background:
        payload = trigger_background_install(force=force)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    return run_install()


def install_status(as_json: bool = False) -> int:
    payload = build_status_payload()
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("Pi 运行时安装状态")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def install_log(tail_lines: int = 40) -> int:
    content = read_install_log_tail(tail_lines)
    if content:
        print(content)
    else:
        print("当前没有可用安装日志。")
    return 0


def interactive_config_wizard() -> int:
    snapshot = _config_snapshot()
    pc_ip = input(f"PC 中枢 IP [{snapshot['network']['pc_ip'] or '留空自动发现'}]: ").strip()
    ws_port = input(f"WebSocket 端口 [{snapshot['network']['ws_port']}]: ").strip()
    wake_word = input(f"唤醒词 [{snapshot['voice']['wake_word']}]: ").strip()
    online_raw = input(f"在线识别 true/false [{'true' if snapshot['voice']['online_recognition'] else 'false'}]: ").strip()
    weights_path = input(f"检测权重 [{snapshot['detector']['weights_path']}]: ").strip()
    detector_conf = input(f"检测阈值 [{snapshot['detector']['conf']}]: ").strip()
    detector_imgsz = input(f"检测尺寸 [{snapshot['detector']['imgsz']}]: ").strip()

    if pc_ip:
        set_pi_config("network.pc_ip", pc_ip)
    if ws_port:
        set_pi_config("network.ws_port", ws_port)
    if wake_word:
        set_pi_config("voice.wake_word", wake_word)
    if online_raw:
        set_pi_config("voice.online_recognition", _parse_bool(online_raw))
    if weights_path:
        set_pi_config("detector.weights_path", weights_path)
    if detector_conf:
        set_pi_config("detector.conf", detector_conf)
    if detector_imgsz:
        set_pi_config("detector.imgsz", detector_imgsz)

    print("配置已保存。")
    return 0


def interactive_menu() -> int:
    while True:
        print("\n=== NeuroLab Hub Pi 交互菜单 ===")
        print("1. 查看状态")
        print("2. 运行自检")
        print("3. 查看配置")
        print("4. 修改配置")
        print("5. 启动边缘端")
        print("0. 退出")
        choice = input("请选择操作 [0-5]: ").strip()
        if choice == "1":
            show_status(as_json=False)
        elif choice == "2":
            run_self_check()
        elif choice == "3":
            show_config(as_json=False)
        elif choice == "4":
            interactive_config_wizard()
        elif choice == "5":
            skip = input("启动前跳过自检? [y/N]: ").strip().lower() in {"y", "yes"}
            return start_node(skip_self_check=skip)
        elif choice == "0":
            return 0
        else:
            print("无效选项，请重新输入。")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="labdetector-pi", description="NeuroLab Hub 树莓派边缘端交互工具")
    subparsers = parser.add_subparsers(dest="command")

    status_parser = subparsers.add_parser("status", help="查看当前配置与节点状态摘要")
    status_parser.add_argument("--json", action="store_true", help="以 JSON 输出")

    config_parser = subparsers.add_parser("config", help="查看或修改边缘端配置")
    config_subparsers = config_parser.add_subparsers(dest="config_command")

    config_show_parser = config_subparsers.add_parser("show", help="显示当前配置")
    config_show_parser.add_argument("--json", action="store_true", help="以 JSON 输出")

    config_set_parser = config_subparsers.add_parser("set", help="设置单个配置项")
    config_set_parser.add_argument("key", help="配置路径，如 network.pc_ip")
    config_set_parser.add_argument("value", help="配置值")

    self_check_parser = subparsers.add_parser("self-check", help="执行树莓派边缘端自检")
    self_check_group = self_check_parser.add_mutually_exclusive_group()
    self_check_group.add_argument("--auto-install-deps", dest="auto_install_deps", action="store_true", help="自检时自动安装缺失依赖")
    self_check_group.add_argument("--no-auto-install-deps", dest="auto_install_deps", action="store_false", help="自检时不自动安装依赖")
    self_check_parser.set_defaults(auto_install_deps=None)

    start_parser = subparsers.add_parser("start", help="启动边缘端服务")
    start_parser.add_argument("--skip-self-check", action="store_true", help="启动前跳过自检")
    start_group = start_parser.add_mutually_exclusive_group()
    start_group.add_argument("--auto-install-deps", dest="auto_install_deps", action="store_true", help="启动前自检时自动安装缺失依赖")
    start_group.add_argument("--no-auto-install-deps", dest="auto_install_deps", action="store_false", help="启动前自检时不自动安装依赖")
    start_parser.set_defaults(auto_install_deps=None)
    start_parser.add_argument("--pc-ip", help="覆盖中枢 IP，并写入配置文件")
    start_parser.add_argument("--ws-port", help="覆盖 WebSocket 端口，并写入配置文件")
    start_parser.add_argument("--wake-word", help="覆盖唤醒词，并写入配置文件")
    start_parser.add_argument("--online-recognition", type=_parse_bool, help="覆盖在线识别开关，并写入配置文件")
    start_parser.add_argument("--weights-path", help="覆盖检测权重路径，并写入配置文件")
    start_parser.add_argument("--detector-conf", type=float, help="覆盖检测阈值，并写入配置文件")
    start_parser.add_argument("--detector-imgsz", type=int, help="覆盖检测尺寸，并写入配置文件")

    install_runtime_parser = subparsers.add_parser("install-runtime", help="执行或触发 Pi 运行时安装")
    install_runtime_parser.add_argument("--background", action="store_true", help="后台触发安装后立即返回")
    install_runtime_parser.add_argument("--force", action="store_true", help="即使已完成也强制重新执行")

    install_status_parser = subparsers.add_parser("install-status", help="查看 Pi 运行时安装状态")
    install_status_parser.add_argument("--json", action="store_true", help="以 JSON 输出")

    install_log_parser = subparsers.add_parser("install-log", help="查看 Pi 运行时安装日志")
    install_log_parser.add_argument("--tail", type=int, default=40, help="输出最后 N 行日志")

    subparsers.add_parser("version", help="输出版本号")
    return parser


def main(argv: list[str] | None = None) -> int:
    raw_args = list(argv if argv is not None else sys.argv[1:])
    if _should_reexec_into_venv():
        return _reexec_into_venv(raw_args)

    parser = build_parser()
    args = parser.parse_args(raw_args)

    try:
        if args.command is None:
            return interactive_menu()
        if args.command == "status":
            return show_status(as_json=args.json)
        if args.command == "config":
            if args.config_command == "show":
                return show_config(as_json=args.json)
            if args.config_command == "set":
                return set_config_value(args.key, args.value)
            parser.error("config 需要子命令 show 或 set")
        if args.command == "self-check":
            return run_self_check(auto_install_deps=getattr(args, "auto_install_deps", None))
        if args.command == "start":
            apply_start_overrides(args)
            return start_node(skip_self_check=args.skip_self_check, auto_install_deps=getattr(args, "auto_install_deps", None))
        if args.command == "install-runtime":
            return install_runtime(background=args.background, force=args.force)
        if args.command == "install-status":
            return install_status(as_json=args.json)
        if args.command == "install-log":
            return install_log(tail_lines=args.tail)
        if args.command == "version":
            print(APP_VERSION)
            return 0
        parser.print_help()
        return 0
    except KeyboardInterrupt:
        print("已中断。")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
