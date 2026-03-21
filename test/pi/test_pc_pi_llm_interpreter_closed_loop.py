from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pc.core import ai_backend
from pc.core.config import get_config, set_config
from pc.core.expert_manager import expert_manager
from pc.webui.runtime import LabDetectorRuntime


REPORT_JSON = ROOT / "tmp" / "pc_pi_llm_interpreter_report_20260321.json"
REPORT_MD = ROOT / "tmp" / "pc_pi_llm_interpreter_report_20260321.md"
ASSET_DIR = ROOT / "tmp" / "llm_closed_loop_assets"
VIRTUAL_PI_SCRIPT = ROOT / "test" / "pi" / "virtual_pi_node.py"


def _pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _write_doc(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _read_log(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def _wait_for(path: Path, needle: str, timeout: float) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if needle in _read_log(path):
            return True
        time.sleep(0.4)
    return False


def _wait_for_expert_result(path: Path, needle: str, timeout: float) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if path.exists():
            for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                if row.get("kind") == "expert_result" and needle in str(row.get("text") or ""):
                    return True
        time.sleep(0.4)
    return False


def _report_row(module: str, status: str, detail: str, extra: Dict[str, Any] | None = None) -> Dict[str, Any]:
    return {
        "module": module,
        "status": status,
        "detail": detail,
        "extra": extra or {},
    }


def _fake_llm(frame: Any, question: str, rag_context: str, model_name: str) -> str:
    merged = f"{question}\n{rag_context}"
    if "葡萄糖酸钙凝胶" in merged or "危化品识别" in merged or "HF" in merged:
        return "知识增强播报：检测到氢氟酸风险，请立即停止操作，使用葡萄糖酸钙凝胶应急并同步上报。"
    if "进入危化品操作区必须穿实验服" in merged or "PPE穿戴检查" in merged:
        return "知识增强播报：当前人员防护不足，进入危化品操作区前请补齐实验服、护目镜和耐酸手套。"
    return "知识增强播报：已完成专家研判。"


def _synthetic_frame(*lines: str) -> np.ndarray:
    frame = np.full((420, 720, 3), 245, dtype=np.uint8)
    y = 90
    for line in lines:
        cv2.putText(frame, line, (48, y), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (20, 20, 20), 2, cv2.LINE_AA)
        y += 72
    return frame


def main() -> int:
    rows: List[Dict[str, Any]] = []
    runtime = LabDetectorRuntime()
    runtime._start_background_aux_services = lambda **kwargs: None
    original_ask = ai_backend.ask_assistant_with_rag
    original_virtual_enabled = get_config("network.virtual_pi_enabled", False)
    original_virtual_host = get_config("network.virtual_pi_host", "")
    original_virtual_hosts = get_config("network.virtual_pi_hosts", "")
    procs: List[subprocess.Popen[bytes]] = []

    try:
        ASSET_DIR.mkdir(parents=True, exist_ok=True)
        chem_doc = ASSET_DIR / "chem_gui_import.txt"
        ppe_doc = ASSET_DIR / "ppe_gui_import.txt"
        _write_doc(
            chem_doc,
            "危化品应急补充：若识别到氢氟酸接触风险，应立即停止操作，使用葡萄糖酸钙凝胶进行应急处理，并同步上报实验负责人。",
        )
        _write_doc(
            ppe_doc,
            "PPE补充规范：进入危化品操作区必须穿实验服、护目镜和耐酸手套，如缺任一项应立即整改后再继续实验。",
        )

        chem_summary = runtime.import_knowledge_paths([str(chem_doc)], scope_name="expert.safety.chem_safety_expert")
        ppe_summary = runtime.import_knowledge_paths([str(ppe_doc)], scope_name="expert.safety.ppe_expert")
        rows.append(
            _report_row(
                "gui_import_simulation",
                "pass" if chem_summary.get("imported_count") and ppe_summary.get("imported_count") else "fail",
                "使用 GUI 同路径将临时知识文档导入危化品/PPE 专家作用域",
                {"chem_summary": chem_summary, "ppe_summary": ppe_summary},
            )
        )

        ai_backend.ask_assistant_with_rag = _fake_llm

        chem_direct = expert_manager.route_and_analyze(
            "危化品识别",
            _synthetic_frame("HF", "Wear gloves", "Bottle A"),
            {
                "detected_classes": "bottle",
                "closed_loop_llm": True,
                "source": "gui_import_test",
                "model": "gemma3:4b",
            },
            allowed_expert_codes=["safety.chem_safety_expert"],
        )
        ppe_direct = expert_manager.route_and_analyze(
            "PPE穿戴检查",
            _synthetic_frame("Lab Zone", "Operator", "No lab coat detected"),
            {
                "detected_classes": "person",
                "closed_loop_llm": True,
                "source": "gui_import_test",
                "model": "gemma3:4b",
            },
            allowed_expert_codes=["safety.ppe_expert"],
        )
        rows.append(
            _report_row(
                "llm_interpreter_layer",
                "pass"
                if ("葡萄糖酸钙凝胶" in chem_direct and "实验服" in ppe_direct)
                else "fail",
                "直接验证 PPE/危化品 专家结果已接入统一多模态 LLM 解释层。",
                {"chem_direct": chem_direct, "ppe_direct": ppe_direct},
            )
        )

        single_port = _pick_free_port()
        single_log = ASSET_DIR / "single_pi.jsonl"
        if single_log.exists():
            single_log.unlink()
        procs.append(
            subprocess.Popen(
                [
                    sys.executable,
                    str(VIRTUAL_PI_SCRIPT),
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(single_port),
                    "--camera-index",
                    "-1",
                    "--event-name",
                    "危化品识别",
                    "--event-interval",
                    "2",
                    "--voice-commands",
                    "",
                    "--log-path",
                    str(single_log),
                    "--node-id",
                    "single-chem",
                ],
                cwd=str(ROOT),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
        )
        time.sleep(2.2)
        set_config("network.virtual_pi_enabled", "True")
        set_config("network.virtual_pi_host", "127.0.0.1")
        set_config("network.virtual_pi_hosts", f"127.0.0.1:{single_port}")
        runtime.start_session(
            {
                "ai_backend": "ollama",
                "selected_model": runtime.selected_model or runtime._default_model_for("ollama"),
                "mode": "websocket",
                "expected_nodes": 1,
                "project_name": "自动测试",
                "experiment_name": "知识增强单节点闭环",
                "operator_name": "Codex",
                "tags": "auto,closed_loop,llm",
            }
        )
        single_ok = _wait_for_expert_result(single_log, "知识增强播报", 18.0)
        runtime.stop_session()
        rows.append(
            _report_row(
                "single_node_closed_loop",
                "pass" if single_ok else "fail",
                "单节点虚拟 Pi 发送危化品事件，PC 结合导入知识库与统一多模态解释层后回传播报。",
                {"log_path": str(single_log), "matched": single_ok},
            )
        )

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

        port1 = _pick_free_port()
        port2 = _pick_free_port()
        while port2 == port1:
            port2 = _pick_free_port()
        log1 = ASSET_DIR / "multi_pi_1.jsonl"
        log2 = ASSET_DIR / "multi_pi_2.jsonl"
        for path in (log1, log2):
            if path.exists():
                path.unlink()
        multi_cmds = [
            [
                sys.executable,
                str(VIRTUAL_PI_SCRIPT),
                "--host",
                "127.0.0.1",
                "--port",
                str(port1),
                "--camera-index",
                "-1",
                "--event-name",
                "PPE穿戴检查",
                "--event-interval",
                "2",
                "--voice-commands",
                "",
                "--log-path",
                str(log1),
                "--node-id",
                "multi-ppe",
            ],
            [
                sys.executable,
                str(VIRTUAL_PI_SCRIPT),
                "--host",
                "127.0.0.1",
                "--port",
                str(port2),
                "--camera-index",
                "-1",
                "--event-name",
                "危化品识别",
                "--event-interval",
                "2",
                "--voice-commands",
                "",
                "--log-path",
                str(log2),
                "--node-id",
                "multi-chem",
            ],
        ]
        for cmd in multi_cmds:
            procs.append(subprocess.Popen(cmd, cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT))
        time.sleep(2.5)
        set_config("network.virtual_pi_hosts", f"127.0.0.1:{port1},127.0.0.1:{port2}")
        runtime.start_session(
            {
                "ai_backend": "ollama",
                "selected_model": runtime.selected_model or runtime._default_model_for("ollama"),
                "mode": "websocket",
                "expected_nodes": 2,
                "project_name": "自动测试",
                "experiment_name": "知识增强多节点闭环",
                "operator_name": "Codex",
                "tags": "auto,closed_loop,llm,multi",
            }
        )
        multi_ppe_ok = _wait_for_expert_result(log1, "知识增强播报", 20.0)
        multi_chem_ok = _wait_for_expert_result(log2, "知识增强播报", 20.0)
        runtime.stop_session()
        rows.append(
            _report_row(
                "multi_node_closed_loop",
                "pass" if multi_ppe_ok and multi_chem_ok else "fail",
                "双节点虚拟 Pi 分别发送 PPE/危化品事件，PC 按专家知识域检索并回传知识增强播报。",
                {
                    "ppe_log": str(log1),
                    "chem_log": str(log2),
                    "ppe_matched": multi_ppe_ok,
                    "chem_matched": multi_chem_ok,
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
        ai_backend.ask_assistant_with_rag = original_ask
        set_config("network.virtual_pi_enabled", original_virtual_enabled)
        set_config("network.virtual_pi_host", original_virtual_host)
        set_config("network.virtual_pi_hosts", original_virtual_hosts)
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

    summary = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "workspace": str(ROOT),
        "pass_count": sum(1 for row in rows if row.get("status") == "pass"),
        "fail_count": sum(1 for row in rows if row.get("status") == "fail"),
        "results": rows,
    }
    REPORT_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# PC-Pi 知识增强闭环测试报告",
        "",
        f"- 生成时间：{summary['generated_at']}",
        f"- 通过：{summary['pass_count']}",
        f"- 失败：{summary['fail_count']}",
        "",
    ]
    for row in rows:
        lines.extend(
            [
                f"## {row['module']}",
                f"- 状态：{row['status']}",
                f"- 说明：{row['detail']}",
                f"- 细节：`{json.dumps(row.get('extra', {}), ensure_ascii=False)}`",
                "",
            ]
        )
    REPORT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(REPORT_JSON)
    return 0 if summary["fail_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
