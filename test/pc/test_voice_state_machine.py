#!/usr/bin/env python3
# -*- coding: utf-8 -*-
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
import pc.voice.voice_interaction as voice_module


REPORT_PATH = ROOT / "tmp" / "voice_state_machine_report.json"


def _pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _latest_voice_note_with(keyword: str) -> Path | None:
    docs_dir = ROOT / "pc" / "knowledge_base" / "docs"
    for note in sorted(docs_dir.glob("VoiceNote_*.txt"), reverse=True):
        text = note.read_text(encoding="utf-8", errors="ignore")
        if keyword in text:
            return note
    return None


def _report(name: str, status: str, detail: str, extra: Dict[str, Any] | None = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"module": name, "status": status, "detail": detail}
    if extra:
        payload["extra"] = extra
    return payload


def main() -> int:
    rows: List[Dict[str, Any]] = []
    runtime = LabDetectorRuntime()
    original_voice_ask = voice_module.ask_assistant_with_rag
    original_virtual_pi_enabled = get_config("network.virtual_pi_enabled", "False")
    original_virtual_pi_host = get_config("network.virtual_pi_host", "127.0.0.1")
    original_virtual_pi_hosts = get_config("network.virtual_pi_hosts", "")
    virtual_pi_proc: subprocess.Popen[bytes] | None = None

    try:
        payload = runtime.bootstrap(include_self_check=False, include_catalogs=False)
        _ = payload
        agent = voice_module.get_voice_interaction()
        if agent is None:
            rows.append(_report("voice_agent_init", "fail", "未能创建语音助手实例"))
            REPORT_PATH.write_text(json.dumps({"results": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
            return 1

        def _fake_voice_ask(frame=None, question="", rag_context="", model_name=""):
            text = str(question or "")
            if "请仅从以下用户口述内容中提取适合写入实验室知识库的有效知识" in text:
                if "移液枪使用后要竖直放置" in text:
                    return json.dumps(["实验规范：移液枪使用后要竖直放置，并及时回架。"], ensure_ascii=False)
                return "[]"
            if "当前系统状态" in text:
                return "PC 数据答复：当前系统状态正常，语音状态机已接管。"
            return "PC 数据答复：已收到。"

        voice_module.ask_assistant_with_rag = _fake_voice_ask

        local_calls: List[str] = []

        def _fake_local_handler(_command: str, intent: str) -> str:
            local_calls.append(intent)
            return f"界面动作已执行：{intent}"

        agent.set_ai_backend("ollama", "gemma3:4b")
        agent.set_local_command_handler(_fake_local_handler)
        agent.open_runtime_session(mode="voice_test", source="pc_local", metadata={"test": True})
        agent.is_active = True

        result = agent.process_text_command("打开知识中心", source="pc_local", speak_response=False)
        local_ok = bool(local_calls and local_calls[-1] == "open_knowledge_center" and "界面动作已执行" in result and agent.is_active)
        rows.append(_report("local_gui_route", "pass" if local_ok else "fail", result, {"calls": local_calls}))

        result = agent.process_text_command("帮我记录 实验规范：移液枪使用后要竖直放置，并及时回架。", source="pc_local", speak_response=False)
        note_pending_ok = ("整理写入知识库" in result and agent.is_active and bool(agent.pending_note_items))
        rows.append(_report("record_pending", "pass" if note_pending_ok else "fail", result, {"pending_count": len(agent.pending_note_items)}))

        result = agent.process_text_command("停止播报", source="pc_local", speak_response=False)
        stop_ok = ("停止当前语音播报" in result and agent.is_active)
        rows.append(_report("control_stop_playback", "pass" if stop_ok else "fail", result, {"is_active": agent.is_active}))

        result = agent.process_text_command("不用了", source="pc_local", speak_response=False)
        note_path = _latest_voice_note_with("移液枪使用后要竖直放置")
        note_text = note_path.read_text(encoding="utf-8", errors="ignore") if note_path else ""
        finalize_ok = ("结束本轮语音交互" in result and (not agent.is_active) and "移液枪使用后要竖直放置" in note_text and "专家结论" not in note_text)
        rows.append(_report("control_stop_session_finalize", "pass" if finalize_ok else "fail", result, {"note_path": str(note_path) if note_path else "", "note_text": note_text}))

        commands_file = ROOT / "tmp" / "voice_state_machine_pi_commands.txt"
        commands_file.write_text(
            "\n".join(
                [
                    "帮我记录 实验规范：移液枪使用后要竖直放置，并及时回架。",
                    "当前系统状态如何",
                    "请识别一下这个化学品标签",
                    "不用了",
                ]
            ),
            encoding="utf-8",
        )
        pi_log = ROOT / "tmp" / "voice_state_machine_pi.jsonl"
        if pi_log.exists():
            pi_log.unlink()

        port = _pick_free_port()
        virtual_pi_script = ROOT / "test" / "pi" / "virtual_pi_node.py"
        virtual_pi_proc = subprocess.Popen(
            [
                sys.executable,
                str(virtual_pi_script),
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--camera-index",
                "-1",
                "--event-interval",
                "0",
                "--voice-commands-file",
                str(commands_file),
                "--voice-start-delay",
                "2",
                "--voice-interval",
                "3",
                "--log-path",
                str(pi_log),
                "--node-id",
                "voice-state",
            ],
            cwd=str(ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )

        set_config("network.virtual_pi_enabled", "True")
        set_config("network.virtual_pi_host", "127.0.0.1")
        set_config("network.virtual_pi_hosts", f"127.0.0.1:{port}")

        runtime.start_session(
            {
                "ai_backend": "ollama",
                "selected_model": runtime.selected_model or runtime._default_model_for("ollama"),
                "mode": "websocket",
                "expected_nodes": 1,
                "project_name": "自动测试",
                "experiment_name": "语音状态机闭环",
                "operator_name": "Codex",
                "tags": "auto,voice_state_machine",
            }
        )

        deadline = time.time() + 18.0
        pi_text = ""
        while time.time() < deadline:
            if pi_log.exists():
                pi_text = pi_log.read_text(encoding="utf-8", errors="ignore")
                if '"kind": "tts_received"' in pi_text and "当前系统状态正常" in pi_text and "结束本轮语音交互" in pi_text:
                    break
            time.sleep(0.5)
        runtime.stop_session()
        time.sleep(1.0)

        pi_note = _latest_voice_note_with("移液枪使用后要竖直放置")
        pi_note_text = pi_note.read_text(encoding="utf-8", errors="ignore") if pi_note else ""
        pi_ok = (
            '"kind": "voice_command_sent"' in pi_text
            and '"kind": "tts_received"' in pi_text
            and "当前系统状态正常" in pi_text
            and "结束本轮语音交互" in pi_text
            and "移液枪使用后要竖直放置" in pi_note_text
            and "专家结论" not in pi_note_text
        )
        rows.append(
            _report(
                "pc_pi_voice_closed_loop",
                "pass" if pi_ok else "fail",
                "虚拟 Pi 语音命令已发送并收到 PC 回传",
                {"pi_log": str(pi_log), "knowledge_note": str(pi_note) if pi_note else "", "pi_log_excerpt": pi_text[-1200:]},
            )
        )
    finally:
        voice_module.ask_assistant_with_rag = original_voice_ask
        try:
            runtime.stop_session()
        except Exception:
            pass
        runtime.shutdown()
        set_config("network.virtual_pi_enabled", original_virtual_pi_enabled)
        set_config("network.virtual_pi_host", original_virtual_pi_host)
        set_config("network.virtual_pi_hosts", original_virtual_pi_hosts)
        if virtual_pi_proc is not None:
            try:
                virtual_pi_proc.terminate()
                virtual_pi_proc.communicate(timeout=5)
            except Exception:
                pass

    fail_count = sum(1 for row in rows if row["status"] == "fail")
    REPORT_PATH.write_text(
        json.dumps(
            {
                "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "pass_count": sum(1 for row in rows if row["status"] == "pass"),
                "fail_count": fail_count,
                "results": rows,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
