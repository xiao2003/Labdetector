from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pc.core.config import get_config, set_config
from pc.webui.runtime import LabDetectorRuntime


REPORT_JSON = ROOT / "tmp" / "pc_pi_integrated_bridge_report_20260321.json"
REPORT_MD = ROOT / "tmp" / "pc_pi_integrated_bridge_report_20260321.md"
VIRTUAL_PI_SCRIPT = ROOT / "test" / "pi" / "virtual_pi_node.py"


def _pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def _write_command_file(path: Path, commands: List[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(commands) + "\n", encoding="utf-8-sig")
    return path


def _wait_for(path: Path, predicates: List[str], timeout: float) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        text = _read_text(path)
        if all(token in text for token in predicates):
            return True
        time.sleep(0.5)
    return False


def _count_occurrences(path: Path, needle: str) -> int:
    return _read_text(path).count(needle)


def _wait_for_runtime_phrase(runtime: LabDetectorRuntime, phrases: List[str], timeout: float) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        summaries = " ".join(str(item.get("text") or "") for item in list(runtime.logs))
        if all(token in summaries for token in phrases):
            return True
        time.sleep(0.4)
    return False


def _wait_for_runtime_count(runtime: LabDetectorRuntime, phrase: str, minimum: int, timeout: float) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        summaries = " ".join(str(item.get("text") or "") for item in list(runtime.logs))
        if summaries.count(phrase) >= minimum:
            return True
        time.sleep(0.4)
    return False


def _row(module: str, status: str, detail: str, extra: Dict[str, Any] | None = None) -> Dict[str, Any]:
    return {"module": module, "status": status, "detail": detail, "extra": extra or {}}


def _latest_voice_note_after(timestamp: float) -> str:
    docs_dir = ROOT / "pc" / "knowledge_base" / "docs"
    candidates = sorted(docs_dir.glob("VoiceNote_*.txt"), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in candidates:
        if path.stat().st_mtime >= timestamp:
            return str(path)
    return ""


def _wait_for_voice_note_after(timestamp: float, timeout: float) -> str:
    deadline = time.time() + timeout
    while time.time() < deadline:
        note_path = _latest_voice_note_after(timestamp)
        if note_path:
            return note_path
        time.sleep(0.5)
    return ""


def _spawn_virtual_pi(
    *,
    port: int,
    log_path: Path,
    node_id: str,
    command_file: Path,
    event_interval: float,
    voice_start_delay: float,
    voice_interval: float,
) -> subprocess.Popen[bytes]:
    cmd = [
        sys.executable,
        str(VIRTUAL_PI_SCRIPT),
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--camera-index",
        "-1",
        "--event-interval",
        str(event_interval),
        "--voice-commands-file",
        str(command_file),
        "--voice-start-delay",
        str(voice_start_delay),
        "--voice-interval",
        str(voice_interval),
        "--log-path",
        str(log_path),
        "--node-id",
        node_id,
    ]
    return subprocess.Popen(cmd, cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def _write_report(rows: List[Dict[str, Any]]) -> int:
    summary = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "pass_count": sum(1 for item in rows if item["status"] == "pass"),
        "fail_count": sum(1 for item in rows if item["status"] == "fail"),
        "results": rows,
    }
    REPORT_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# PC-Pi 一体化闭环测试报告",
        "",
        f"- 生成时间：{summary['generated_at']}",
        f"- 通过：{summary['pass_count']}",
        f"- 失败：{summary['fail_count']}",
        "",
    ]
    for item in rows:
        lines.extend(
            [
                f"## {item['module']}",
                f"- 状态：{item['status']}",
                f"- 说明：{item['detail']}",
                f"- 细节：`{json.dumps(item['extra'], ensure_ascii=False)}`",
                "",
            ]
        )
    REPORT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(REPORT_JSON)
    return 0 if summary["fail_count"] == 0 else 1


def _terminate_all(procs: List[subprocess.Popen[bytes]]) -> None:
    while procs:
        proc = procs.pop()
        try:
            proc.terminate()
            proc.communicate(timeout=5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


def _aggregate_counts(paths: List[Path]) -> Dict[str, int]:
    counts = {"tts": 0, "expert_result": 0, "expert_ack": 0}
    for path in paths:
        counts["tts"] += _count_occurrences(path, "\"kind\": \"tts_received\"")
        counts["expert_result"] += _count_occurrences(path, "\"kind\": \"expert_result\"")
        counts["expert_ack"] += _count_occurrences(path, "\"kind\": \"expert_ack_sent\"")
    return counts


def main() -> int:
    rows: List[Dict[str, Any]] = []
    runtime = LabDetectorRuntime()
    runtime._start_background_aux_services = lambda **kwargs: None
    original_enabled = get_config("network.virtual_pi_enabled", False)
    original_host = get_config("network.virtual_pi_host", "")
    original_hosts = get_config("network.virtual_pi_hosts", "")
    procs: List[subprocess.Popen[bytes]] = []

    try:
        set_config("network.virtual_pi_enabled", "True")
        set_config("network.virtual_pi_host", "127.0.0.1")

        single_port = _pick_free_port()
        single_log = ROOT / "tmp" / "integrated_bridge_single.jsonl"
        single_commands = _write_command_file(
            ROOT / "tmp" / "integrated_bridge_single_commands.txt",
            [
                "帮我记录 实验规范：危化品操作后要立即洗手。",
                "当前系统状态如何",
                "请识别一下这个化学品标签",
                "不用了",
            ],
        )
        if single_log.exists():
            single_log.unlink()
        single_started_at = time.time()
        procs.append(
            _spawn_virtual_pi(
                port=single_port,
                log_path=single_log,
                node_id="bridge-single",
                command_file=single_commands,
                event_interval=4.0,
                voice_start_delay=1.8,
                voice_interval=2.4,
            )
        )
        time.sleep(2.5)
        set_config("network.virtual_pi_hosts", f"127.0.0.1:{single_port}")
        runtime.start_session(
            {
                "ai_backend": "ollama",
                "selected_model": runtime.selected_model or runtime._default_model_for("ollama"),
                "mode": "websocket",
                "expected_nodes": 1,
                "project_name": "自动测试",
                "experiment_name": "PC_PI_单节点通过性",
                "operator_name": "Codex",
                "tags": "auto,bridge,single",
            }
        )

        single_log_ok = _wait_for(
            single_log,
            [
                "\"bridge\": \"pi.testing.closed_loop_bridge\"",
                "\"kind\": \"voice_command_sent\"",
                "\"kind\": \"tts_received\"",
                "\"kind\": \"expert_result\"",
                "\"kind\": \"expert_ack_sent\"",
                "\"index\": 3",
            ],
            60.0,
        )
        single_runtime_ok = _wait_for_runtime_phrase(
            runtime,
            [
                "收到节点 1 语音指令",
                "已回传节点 1 语音播报",
            ],
            50.0,
        )
        runtime.stop_session()
        time.sleep(4.0)
        single_note = _wait_for_voice_note_after(single_started_at, 12.0)
        single_ack_count = _count_occurrences(single_log, "\"kind\": \"expert_ack_sent\"")
        rows.append(
            _row(
                "single_node_pass",
                "pass" if single_log_ok and single_runtime_ok and bool(single_note) and single_ack_count >= 1 else "fail",
                "单节点虚拟 Pi 在弱预览 + 关键帧裁剪模式下完成语音、视觉和知识回传闭环。",
                {
                    "log_path": str(single_log),
                    "runtime_ok": single_runtime_ok,
                    "knowledge_note": single_note,
                    "expert_ack_count": single_ack_count,
                },
            )
        )

        _terminate_all(procs)

        node_specs = [
            {
                "node_id": "stress-1",
                "commands": [
                    "帮我记录 实验规范：进入实验区必须佩戴护目镜。",
                    "当前系统状态如何",
                    "不用了",
                ],
            },
            {
                "node_id": "stress-2",
                "commands": [
                    "帮我记录 实验结束后检查废液桶液位。",
                    "请识别一下这个化学品标签",
                    "不用了",
                ],
            },
            {
                "node_id": "stress-3",
                "commands": [
                    "帮我记录 危化品操作后要及时洗手。",
                    "当前系统状态如何",
                    "不用了",
                ],
            },
            {
                "node_id": "stress-4",
                "commands": [
                    "帮我记录 实验服污染后要及时更换。",
                    "请识别一下这个化学品标签",
                    "不用了",
                ],
            },
        ]

        multi_hosts: List[str] = []
        multi_logs: List[Path] = []
        for index, spec in enumerate(node_specs, start=1):
            port = _pick_free_port()
            log_path = ROOT / "tmp" / f"integrated_bridge_stress_{index}.jsonl"
            cmd_path = ROOT / "tmp" / f"integrated_bridge_stress_{index}_commands.txt"
            if log_path.exists():
                log_path.unlink()
            _write_command_file(cmd_path, spec["commands"])
            procs.append(
                _spawn_virtual_pi(
                    port=port,
                    log_path=log_path,
                    node_id=str(spec["node_id"]),
                    command_file=cmd_path,
                    event_interval=3.0,
                    voice_start_delay=1.4 + index * 0.4,
                    voice_interval=1.8,
                )
            )
            multi_hosts.append(f"127.0.0.1:{port}")
            multi_logs.append(log_path)

        time.sleep(3.0)
        set_config("network.virtual_pi_hosts", ",".join(multi_hosts))
        runtime.start_session(
            {
                "ai_backend": "ollama",
                "selected_model": runtime.selected_model or runtime._default_model_for("ollama"),
                "mode": "websocket",
                "expected_nodes": len(node_specs),
                "project_name": "自动测试",
                "experiment_name": "PC_PI_多节点压力",
                "operator_name": "Codex",
                "tags": "auto,bridge,stress",
            }
        )

        log_checks = []
        for log_path in multi_logs:
            ok = _wait_for(
                log_path,
                [
                    "\"bridge\": \"pi.testing.closed_loop_bridge\"",
                    "\"kind\": \"voice_command_sent\"",
                    "\"kind\": \"tts_received\"",
                ],
                45.0,
            )
            log_checks.append(ok)

        runtime_multi_ok = _wait_for_runtime_count(runtime, "已回传节点", 4, 55.0)
        counts = _aggregate_counts(multi_logs)
        expert_deadline = time.time() + 25.0
        while time.time() < expert_deadline and counts["expert_result"] < 1 and counts["expert_ack"] < 1:
            counts = _aggregate_counts(multi_logs)
            time.sleep(0.5)
        runtime.stop_session()
        rows.append(
            _row(
                "multi_node_stress",
                "pass"
                if all(log_checks)
                and runtime_multi_ok
                and counts["tts"] >= len(node_specs)
                and (counts["expert_result"] >= 1 or counts["expert_ack"] >= 1)
                else "fail",
                "四节点虚拟 Pi 在弱预览 + 关键帧裁剪模式下完成并发压力闭环，PC 串行处理并回传播报。",
                {
                    "log_paths": [str(path) for path in multi_logs],
                    "per_node_ok": log_checks,
                    "runtime_ok": runtime_multi_ok,
                    "expert_ack_count": counts["expert_ack"],
                    "expert_result_count": counts["expert_result"],
                    "tts_count": counts["tts"],
                    "node_count": len(node_specs),
                },
            )
        )
    finally:
        try:
            if runtime.session_active:
                runtime.stop_session()
        except Exception:
            pass
        runtime.shutdown()
        set_config("network.virtual_pi_enabled", original_enabled)
        set_config("network.virtual_pi_host", original_host)
        set_config("network.virtual_pi_hosts", original_hosts)
        _terminate_all(procs)

    return _write_report(rows)


if __name__ == "__main__":
    raise SystemExit(main())
