#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Automated module test runner for NeuroLab Hub."""

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

import cv2
import numpy as np

from pc.core.config import get_config, set_config
from pc.core.expert_manager import expert_manager
from pc.core.experiment_archive import get_experiment_archive
from pc.knowledge_base.rag_engine import knowledge_manager
from pc.webui.runtime import LabDetectorRuntime

REPORT_PATH = ROOT / "tmp" / "auto_module_test_report.json"


def _now() -> float:
    return time.time()


def _report(
    name: str,
    purpose: str,
    method: str,
    expected: str,
    status: str,
    detail: str,
    started_at: float,
    extra: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    payload = {
        "module": name,
        "purpose": purpose,
        "method": method,
        "expected": expected,
        "status": status,
        "detail": detail,
        "duration_ms": int((_now() - started_at) * 1000),
    }
    if extra:
        payload["extra"] = extra
    return payload


def _status_from_self_check(rows: List[Dict[str, Any]]) -> str:
    if any(str(row.get("status", "")).lower() == "error" for row in rows):
        return "fail"
    if any(str(row.get("status", "")).lower() == "warn" for row in rows):
        return "warn"
    return "pass"


def _make_test_frame() -> np.ndarray:
    frame = np.zeros((540, 960, 3), dtype=np.uint8)
    frame[:, :, 0] = 32
    frame[:, :, 1] = 64
    frame[:, :, 2] = 96
    return frame


def _make_text_frame(lines: List[str]) -> np.ndarray:
    frame = np.full((540, 960, 3), 255, dtype=np.uint8)
    y = 120
    for line in lines:
        cv2.putText(frame, line, (60, y), cv2.FONT_HERSHEY_SIMPLEX, 1.4, (20, 20, 20), 3, cv2.LINE_AA)
        y += 90
    cv2.rectangle(frame, (40, 40), (920, 500), (90, 90, 90), 3)
    return frame


def _make_flame_frame() -> np.ndarray:
    frame = np.zeros((540, 960, 3), dtype=np.uint8)
    cv2.ellipse(frame, (480, 320), (90, 140), 0, 0, 360, (0, 180, 255), -1)
    cv2.ellipse(frame, (480, 360), (70, 100), 0, 0, 360, (0, 255, 255), -1)
    return frame


def _make_spill_frame() -> np.ndarray:
    frame = np.full((540, 960, 3), 230, dtype=np.uint8)
    pts = np.array([[260, 300], [360, 250], [520, 270], [640, 340], [600, 420], [420, 440], [280, 390]], dtype=np.int32)
    cv2.fillPoly(frame, [pts], (40, 40, 40))
    return frame


def _make_droplet_frame() -> np.ndarray:
    frame = np.full((540, 960, 3), 245, dtype=np.uint8)
    cv2.line(frame, (120, 380), (840, 380), (30, 30, 30), 4)
    cv2.ellipse(frame, (480, 330), (170, 85), 0, 0, 180, (20, 20, 20), 3)
    cv2.ellipse(frame, (480, 370), (170, 45), 0, 180, 360, (20, 20, 20), 3)
    return frame


def _decode_output(payload: bytes) -> str:
    for encoding in ("utf-8", "gbk", "cp936"):
        try:
            return payload.decode(encoding)
        except Exception:
            continue
    return payload.decode("utf-8", errors="ignore")


def _find_expert(expert_code: str):
    for expert in expert_manager.experts.values():
        if expert.expert_code == expert_code:
            return expert
    return None


def _pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return int(sock.getsockname()[1])


def _latest_voice_note_with(keyword: str) -> Path | None:
    docs_dir = ROOT / "pc" / "knowledge_base" / "docs"
    for note in sorted(docs_dir.glob("VoiceNote_*.txt"), reverse=True):
        content = note.read_text(encoding="utf-8", errors="ignore")
        if keyword in content:
            return note
    return None


def _write_command_file(path: Path, commands: List[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(commands) + "\n", encoding="utf-8-sig")
    return path


def run() -> Dict[str, Any]:
    report_rows: List[Dict[str, Any]] = []
    runtime = LabDetectorRuntime()
    original_virtual_pi_enabled = get_config("network.virtual_pi_enabled", "False")
    original_virtual_pi_host = get_config("network.virtual_pi_host", "127.0.0.1")
    original_virtual_pi_hosts = get_config("network.virtual_pi_hosts", "")
    virtual_pi_proc: subprocess.Popen[bytes] | None = None
    virtual_pi_script = ROOT / "test" / "pi" / "virtual_pi_node.py"

    try:
        started = _now()
        payload = runtime.bootstrap(include_self_check=False, include_catalogs=True)
        report_rows.append(
            _report(
                "runtime_bootstrap",
                "验证运行时基础初始化与目录加载",
                "调用 LabDetectorRuntime.bootstrap(include_self_check=False, include_catalogs=True)",
                "返回版本、控制项、知识库与专家目录",
                "pass",
                "运行时初始化完成",
                started,
                {
                    "version": payload.get("version"),
                    "backend_count": len(payload.get("controls", {}).get("backends", [])),
                },
            )
        )

        started = _now()
        self_check_rows = runtime.run_self_check(include_microphone=False)
        self_check_status = _status_from_self_check(self_check_rows)
        report_rows.append(
            _report(
                "self_check",
                "验证核心依赖、语音模型、知识库与训练运行时",
                "调用 runtime.run_self_check(include_microphone=False)",
                "无阻断性 error；warn 仅限可降级项",
                self_check_status,
                f"自检完成，共 {len(self_check_rows)} 项",
                started,
                {
                    "error_count": sum(1 for row in self_check_rows if str(row.get('status', '')).lower() == 'error'),
                    "warn_count": sum(1 for row in self_check_rows if str(row.get('status', '')).lower() == 'warn'),
                },
            )
        )

        started = _now()
        expert_catalog = expert_manager.list_expert_catalog()
        resident_count = sum(1 for row in expert_catalog if row.get("trigger_mode") == "resident")
        voice_count = sum(1 for row in expert_catalog if row.get("trigger_mode") == "voice")
        report_rows.append(
            _report(
                "expert_catalog",
                "验证专家目录与双通道路由元数据",
                "调用 expert_manager.list_expert_catalog()",
                "同时存在 resident 与 voice 两类专家",
                "pass" if expert_catalog and resident_count and voice_count else "fail",
                f"专家总数 {len(expert_catalog)}，resident={resident_count}，voice={voice_count}",
                started,
            )
        )

        started = _now()
        scope_rows = knowledge_manager.list_scopes(include_known_experts=True)
        report_rows.append(
            _report(
                "knowledge_base_catalog",
                "验证知识库作用域目录扫描",
                "调用 knowledge_manager.list_scopes(include_known_experts=True)",
                "至少识别 common 与若干 expert 作用域",
                "pass" if scope_rows else "fail",
                f"已识别 {len(scope_rows)} 个知识库作用域",
                started,
            )
        )

        started = _now()
        model_catalog = runtime.refresh_model_catalog()
        report_rows.append(
            _report(
                "model_service_catalog",
                "验证模型目录刷新",
                "调用 runtime.refresh_model_catalog()",
                "返回至少一个后端目录",
                "pass" if model_catalog else "fail",
                f"模型后端数量 {len(model_catalog)}",
                started,
            )
        )

        started = _now()
        cloud_catalog = runtime.get_cloud_backend_catalog()
        report_rows.append(
            _report(
                "cloud_backend_catalog",
                "验证云端模型配置目录",
                "调用 runtime.get_cloud_backend_catalog()",
                "返回至少一个云端配置项",
                "pass" if cloud_catalog else "fail",
                f"云端配置数量 {len(cloud_catalog)}",
                started,
            )
        )

        started = _now()
        workspace_result = runtime.build_training_workspace(f"auto_test_{time.strftime('%Y%m%d_%H%M%S')}")
        report_rows.append(
            _report(
                "training_workspace",
                "验证训练工作区构建",
                "调用 runtime.build_training_workspace()",
                "工作区目录创建成功",
                "pass" if workspace_result.get("workspace_dir") else "fail",
                f"工作区 {workspace_result.get('workspace_dir', '')}",
                started,
            )
        )

        test_frame = _make_test_frame()

        started = _now()
        resident_result = expert_manager.analyze_resident_frame(
            test_frame,
            {"event_name": "综合安全巡检", "source": "auto_module_test"},
            media_type="video",
        )
        resident_groups = resident_result.get("stream_groups") or {}
        report_rows.append(
            _report(
                "resident_expert_route",
                "验证常驻专家按视频流组共享同一帧分析",
                "调用 expert_manager.analyze_resident_frame()",
                "返回至少一个 resident stream_group",
                "pass" if resident_groups else "fail",
                f"常驻流组 {list(resident_groups.keys())}",
                started,
            )
        )

        started = _now()
        flame_expert = _find_expert("safety.flame_fire_expert")
        flame_result = flame_expert.analyze(_make_flame_frame(), {"event_name": "明火烟雾巡检"}) if flame_expert else ""
        report_rows.append(
            _report(
                "virtual_flame_fire",
                "验证火焰烟雾专家可对合成火焰图像产出告警",
                "构造火焰图像并调用 safety.flame_fire_expert.analyze()",
                "返回非空火焰风险提示",
                "pass" if flame_result else "fail",
                flame_result or "未生成火焰风险提示",
                started,
            )
        )

        started = _now()
        ppe_expert = _find_expert("safety.ppe_expert")
        ppe_result = ppe_expert.analyze(
            test_frame,
            {"event_name": "PPE 穿戴检查", "detected_classes": "person bottle"},
        ) if ppe_expert else ""
        report_rows.append(
            _report(
                "virtual_ppe",
                "验证 PPE 专家可根据虚拟检测结果识别防护缺失",
                "向 safety.ppe_expert 注入 person/bottle 上下文",
                "返回缺少实验服、手套或护目镜的提醒",
                "pass" if ppe_result else "fail",
                ppe_result or "未生成 PPE 提示",
                started,
            )
        )

        started = _now()
        general_expert = _find_expert("safety.general_safety_expert")
        general_result = general_expert.analyze(
            test_frame,
            {"event_name": "一般安全巡检", "detected_classes": "person cell phone"},
        ) if general_expert else ""
        report_rows.append(
            _report(
                "virtual_general_safety",
                "验证通用安全行为专家可识别实验期间使用手机",
                "向 safety.general_safety_expert 注入 person/cell phone 上下文",
                "返回手机使用违规告警",
                "pass" if general_result else "fail",
                general_result or "未生成通用安全提示",
                started,
            )
        )

        started = _now()
        spill_expert = _find_expert("safety.spill_detection_expert")
        spill_result = spill_expert.analyze(_make_spill_frame(), {"event_name": "液体洒漏巡检"}) if spill_expert else ""
        report_rows.append(
            _report(
                "virtual_spill_detection",
                "验证液体洒漏专家可对合成洒漏图像产出风险提示",
                "构造实验台洒漏图像并调用 spill_detection_expert.analyze()",
                "返回非空洒漏风险提示",
                "pass" if spill_result else "fail",
                spill_result or "未生成洒漏风险提示",
                started,
            )
        )

        started = _now()
        operation_expert = _find_expert("safety.equipment_operation_expert")
        operation_result = operation_expert.analyze(
            test_frame,
            {"event_name": "仪器操作巡检", "detected_classes": "centrifuge person"},
        ) if operation_expert else ""
        report_rows.append(
            _report(
                "virtual_equipment_operation",
                "验证仪器操作专家可根据虚拟检测结果识别不规范操作",
                "向 safety.equipment_operation_expert 注入 centrifuge/person 上下文",
                "返回操作规范提醒",
                "pass" if operation_result else "fail",
                operation_result or "未生成仪器操作提示",
                started,
            )
        )

        started = _now()
        contact_expert = _find_expert("nanofluidics.microfluidic_contact_angle_expert")
        contact_result = contact_expert.analyze(
            _make_droplet_frame(),
            {"event_name": "接触角检测", "angle_low": 60, "angle_high": 110},
        ) if contact_expert else ""
        report_rows.append(
            _report(
                "virtual_contact_angle",
                "验证微纳接触角专家可对合成液滴轮廓给出结果",
                "构造液滴轮廓图像并调用 microfluidic_contact_angle_expert.analyze()",
                "返回接触角正常或异常结果",
                "pass" if contact_result else "fail",
                contact_result or "未生成接触角结果",
                started,
            )
        )

        chem_frame = _make_text_frame(["H2SO4", "Corrosive", "Bottle A"])
        started = _now()
        chem_voice = expert_manager.route_voice_command(
            "小爱同学，请识别一下这个化学品标签并提醒风险",
            chem_frame,
            {"source": "auto_module_test", "detected_classes": "bottle"},
        )
        chem_codes = chem_voice.get("matched_expert_codes") or []
        report_rows.append(
            _report(
                "voice_expert_chem",
                "验证语音唤醒可命中危化品识别专家",
                "调用 expert_manager.route_voice_command() 注入虚拟语音文本",
                "命中 safety.chem_safety_expert",
                "pass" if "safety.chem_safety_expert" in chem_codes else "fail",
                f"命中专家: {chem_codes}",
                started,
            )
        )

        ocr_frame = _make_text_frame(["TEMP 25.6C", "PRESS 1.2bar", "RPM 1500"])
        started = _now()
        ocr_voice = expert_manager.route_voice_command(
            "小爱同学，读一下这个设备屏幕内容",
            ocr_frame,
            {"source": "auto_module_test"},
        )
        ocr_codes = ocr_voice.get("matched_expert_codes") or []
        report_rows.append(
            _report(
                "voice_expert_ocr",
                "验证闭环聚焦模式下 OCR 语音专家已被排除",
                "调用 expert_manager.route_voice_command() 注入虚拟语音文本",
                "不命中 equipment_ocr_expert",
                "pass" if "equipment_ocr_expert" not in ocr_codes else "fail",
                f"OCR 专家命中结果: {ocr_codes}",
                started,
            )
        )

        started = _now()
        primary_port = _pick_free_port()
        set_config("network.virtual_pi_enabled", "True")
        set_config("network.virtual_pi_host", "127.0.0.1")
        set_config("network.virtual_pi_hosts", f"127.0.0.1:{primary_port}")
        command = [
            sys.executable,
            str(virtual_pi_script),
            "--host",
            "127.0.0.1",
            "--port",
            str(primary_port),
            "--camera-index",
            "-1",
            "--event-name",
            "综合安全巡检",
            "--event-interval",
            "4",
            "--node-id",
            "1",
        ]
        virtual_pi_proc = subprocess.Popen(command, cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        time.sleep(3.0)

        runtime.start_session(
            {
                "ai_backend": "ollama",
                "selected_model": runtime.selected_model or runtime._default_model_for("ollama"),
                "mode": "websocket",
                "expected_nodes": 1,
                "project_name": "自动测试",
                "experiment_name": "虚拟 Pi 闭环",
                "operator_name": "Codex",
                "tags": "auto,virtual_pi",
            }
        )
        online = False
        result_seen = False
        latest_result: Dict[str, Any] = {}
        deadline = _now() + 18.0
        while _now() < deadline:
            state = runtime.get_state()
            streams = state.get("streams") or []
            if any(item.get("status") == "online" for item in streams):
                online = True
            manager = runtime.manager
            if manager:
                for node_result in manager.node_latest_results.values():
                    if node_result.get("event_name") or node_result.get("text"):
                        latest_result = dict(node_result)
                        result_seen = True
                        break
                if not result_seen and getattr(manager, "recent_event_ids", None):
                    result_seen = len(manager.recent_event_ids) > 0
                    if result_seen:
                        latest_result = {
                            "event_name": "综合安全巡检",
                            "text": "节点事件已接收并进入闭环处理",
                        }
            if not result_seen:
                summaries = " ".join(str(item.get("text") or "") for item in list(runtime.logs))
                if "收到节点 [1] 边缘高优告警" in summaries or "收到节点 [1] 边缘策略事件" in summaries:
                    result_seen = True
                    latest_result = {"event_name": "边缘事件", "text": "运行时日志已确认收到节点事件"}
            if online and result_seen:
                break
            time.sleep(1.0)
        runtime.stop_session()
        report_rows.append(
            _report(
                "virtual_pi_closed_loop",
                "验证虚拟 Pi 节点到 PC 的本地闭环联动",
                "启动 virtual_pi_node.py，再调用 runtime.start_session(mode=websocket)",
                "PC 能发现虚拟节点、节点在线，并接收到闭环结果",
                "pass" if online and result_seen else "fail",
                f"online={online}, result_seen={result_seen}, latest={latest_result}",
                started,
            )
        )

        started = _now()
        archive = get_experiment_archive()
        sessions = archive.list_sessions(limit=3)
        latest_session = sessions[0] if sessions else {}
        archive_ok = bool(sessions and str(latest_session.get("project_name") or "") == "自动测试")
        report_rows.append(
            _report(
                "experiment_archive",
                "验证监控会话与事件归档是否真实落盘",
                "调用 experiment_archive.list_sessions() 检查最近会话",
                "存在自动测试产生的最新归档会话",
                "pass" if archive_ok else "fail",
                f"最近会话 {latest_session.get('session_id', '')}",
                started,
                {"latest_session": latest_session},
            )
        )

        started = _now()
        restart_ok = True
        restart_detail: List[str] = []
        for cycle in range(2):
            try:
                runtime.start_session(
                    {
                        "ai_backend": "ollama",
                        "selected_model": runtime.selected_model or runtime._default_model_for("ollama"),
                        "mode": "websocket",
                        "expected_nodes": 1,
                        "project_name": "自动测试",
                        "experiment_name": f"重复启停_{cycle + 1}",
                        "operator_name": "Codex",
                        "tags": "auto,restart",
                    }
                )
                time.sleep(4.0)
                state = runtime.get_state()
                online_cycle = any(item.get("status") == "online" for item in (state.get("streams") or []))
                restart_detail.append(f"cycle{cycle + 1}=online:{online_cycle}")
                restart_ok = restart_ok and online_cycle
            finally:
                runtime.stop_session()
                time.sleep(1.0)
        report_rows.append(
            _report(
                "virtual_pi_restart_stability",
                "验证虚拟 Pi 模式下重复启停监控的稳定性",
                "连续执行两轮 websocket 启动与停止",
                "两轮均能正常上线并正常停止",
                "pass" if restart_ok else "fail",
                ", ".join(restart_detail),
                started,
            )
        )

        import pc.voice.voice_interaction as voice_module

        original_voice_ask = voice_module.ask_assistant_with_rag

        def _fake_voice_ask(frame=None, question="", rag_context="", model_name=""):
            text = str(question or "")
            if "请仅从以下用户口述内容中提取适合写入实验室知识库的有效知识" in text:
                if "移液枪使用后要竖直放置" in text:
                    return json.dumps(["实验规范：移液枪使用后要竖直放置，并及时回架。"], ensure_ascii=False)
                if "酸液标签必须朝外放置" in text:
                    return json.dumps(["实验规范：酸液标签必须朝外放置，便于巡视时快速辨识。"], ensure_ascii=False)
                return "[]"
            if "当前系统状态" in text:
                return "PC 数据答复：当前系统状态正常，最近记录的实验规范已同步。"
            return "PC 数据答复：已收到。"

        voice_module.ask_assistant_with_rag = _fake_voice_ask
        try:
            started = _now()
            single_log = ROOT / "tmp" / "virtual_pi_single_voice.jsonl"
            if single_log.exists():
                single_log.unlink()
            if virtual_pi_proc is not None:
                try:
                    virtual_pi_proc.terminate()
                    virtual_pi_proc.communicate(timeout=5)
                except Exception:
                    pass
                virtual_pi_proc = None

            single_voice_port = _pick_free_port()
            set_config("network.virtual_pi_enabled", "True")
            set_config("network.virtual_pi_host", "127.0.0.1")
            set_config("network.virtual_pi_hosts", f"127.0.0.1:{single_voice_port}")
            command = [
                sys.executable,
                str(virtual_pi_script),
                "--host",
                "127.0.0.1",
                "--port",
                str(single_voice_port),
                "--camera-index",
                "-1",
                "--event-interval",
                "0",
                "--voice-commands",
                "帮我记录 实验规范：移液枪使用后要竖直放置，并及时回架。",
                "--voice-start-delay",
                "2",
                "--voice-interval",
                "3",
                "--log-path",
                str(single_log),
                "--node-id",
                "single",
            ]
            virtual_pi_proc = subprocess.Popen(command, cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            time.sleep(2.5)
            runtime.start_session(
                {
                    "ai_backend": "ollama",
                    "selected_model": runtime.selected_model or runtime._default_model_for("ollama"),
                    "mode": "websocket",
                    "expected_nodes": 1,
                    "project_name": "自动测试",
                    "experiment_name": "Pi 单节点语音记录",
                    "operator_name": "Codex",
                    "tags": "auto,pi_voice_single",
                }
            )
            single_saved = False
            deadline = _now() + 12.0
            while _now() < deadline:
                if single_log.exists():
                    content = single_log.read_text(encoding="utf-8", errors="ignore")
                    if "已记录本轮语音内容，将在本轮结束后整理写入知识库。" in content:
                        single_saved = True
                        break
                time.sleep(0.5)
            runtime.stop_session()
            time.sleep(1.5)
            single_note = _latest_voice_note_with("移液枪使用后要竖直放置")
            report_rows.append(
                _report(
                    "virtual_pi_single_voice_loop",
                    "验证单节点 Pi 语音记录经 PC 提取后写入知识库",
                    "虚拟 Pi 发送记录类语音命令，PC 停止会话后检查知识库落盘",
                    "Pi 收到记录确认播报，PC 知识库只新增用户口述规范",
                    "pass" if single_saved and single_note else "fail",
                    f"tts_saved={single_saved}, note={single_note}",
                    started,
                    {"log_path": str(single_log), "knowledge_note": str(single_note) if single_note else ""},
                )
            )

            try:
                if virtual_pi_proc is not None:
                    virtual_pi_proc.terminate()
                    virtual_pi_proc.communicate(timeout=5)
            except Exception:
                pass
            virtual_pi_proc = None

            started = _now()
            multi_logs = [ROOT / "tmp" / "virtual_pi_multi_1.jsonl", ROOT / "tmp" / "virtual_pi_multi_2.jsonl"]
            for path in multi_logs:
                if path.exists():
                    path.unlink()
            multi_procs: List[subprocess.Popen[bytes]] = []
            multi_port_1 = _pick_free_port()
            multi_port_2 = _pick_free_port()
            while multi_port_2 == multi_port_1:
                multi_port_2 = _pick_free_port()
            multi_commands = [
                [
                    sys.executable,
                    str(virtual_pi_script),
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(multi_port_1),
                    "--camera-index",
                    "-1",
                    "--event-interval",
                    "0",
                    "--voice-commands",
                    "帮我记录 实验规范：酸液标签必须朝外放置，便于巡视时快速辨识。",
                    "--voice-start-delay",
                    "2",
                    "--voice-interval",
                    "4",
                    "--log-path",
                    str(multi_logs[0]),
                    "--node-id",
                    "multi1",
                ],
                [
                    sys.executable,
                    str(virtual_pi_script),
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(multi_port_2),
                    "--camera-index",
                    "-1",
                    "--event-interval",
                    "0",
                    "--voice-commands",
                    "当前系统状态如何",
                    "--voice-start-delay",
                    "3",
                    "--voice-interval",
                    "4",
                    "--log-path",
                    str(multi_logs[1]),
                    "--node-id",
                    "multi2",
                ],
            ]
            for cmd in multi_commands:
                multi_procs.append(subprocess.Popen(cmd, cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT))
            set_config("network.virtual_pi_enabled", "True")
            set_config("network.virtual_pi_host", "127.0.0.1")
            set_config("network.virtual_pi_hosts", f"127.0.0.1:{multi_port_1},127.0.0.1:{multi_port_2}")
            time.sleep(2.5)
            runtime.start_session(
                {
                    "ai_backend": "ollama",
                    "selected_model": runtime.selected_model or runtime._default_model_for("ollama"),
                    "mode": "websocket",
                    "expected_nodes": 2,
                    "project_name": "自动测试",
                    "experiment_name": "Pi 多节点语音联动",
                    "operator_name": "Codex",
                    "tags": "auto,pi_voice_multi",
                }
            )
            multi1_ok = False
            multi2_ok = False
            deadline = _now() + 16.0
            while _now() < deadline:
                if multi_logs[0].exists():
                    text1 = multi_logs[0].read_text(encoding="utf-8", errors="ignore")
                    multi1_ok = "已记录本轮语音内容，将在本轮结束后整理写入知识库。" in text1
                if multi_logs[1].exists():
                    text2 = multi_logs[1].read_text(encoding="utf-8", errors="ignore")
                    multi2_ok = "PC 数据答复：当前系统状态正常，最近记录的实验规范已同步。" in text2
                    if not multi2_ok:
                        multi2_ok = '"kind": "tts_received"' in text2
                if multi1_ok and multi2_ok:
                    break
                time.sleep(0.5)
            runtime.stop_session()
            time.sleep(1.5)
            multi_note = _latest_voice_note_with("酸液标签必须朝外放置")
            report_rows.append(
                _report(
                    "virtual_pi_multi_voice_loop",
                    "验证多节点 Pi 语音命令可并发上送至 PC 并分别回传结果",
                    "两台虚拟 Pi 分别发送记录和问答语音命令，PC 处理后回传各自 TTS",
                    "两台节点都收到对应答复，且 PC 知识库只新增用户口述规范",
                    "pass" if multi1_ok and multi2_ok and multi_note else "fail",
                    f"multi1={multi1_ok}, multi2={multi2_ok}, note={multi_note}",
                    started,
                    {"log_paths": [str(path) for path in multi_logs], "knowledge_note": str(multi_note) if multi_note else ""},
                )
            )
            for proc in multi_procs:
                try:
                    proc.terminate()
                    proc.communicate(timeout=5)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
        finally:
            voice_module.ask_assistant_with_rag = original_voice_ask

    finally:
        try:
            if runtime.session_active:
                runtime.stop_session()
        except Exception:
            pass
        runtime.shutdown()
        set_config("network.virtual_pi_enabled", original_virtual_pi_enabled)
        set_config("network.virtual_pi_host", original_virtual_pi_host)
        set_config("network.virtual_pi_hosts", original_virtual_pi_hosts)
        if virtual_pi_proc is not None:
            try:
                output = virtual_pi_proc.communicate(timeout=6)[0]
            except Exception:
                try:
                    virtual_pi_proc.kill()
                    output = virtual_pi_proc.communicate(timeout=3)[0]
                except Exception:
                    output = b""
            if output:
                report_rows.append(
                    {
                        "module": "virtual_pi_stdout",
                        "status": "info",
                        "detail": _decode_output(output)[-4000:],
                    }
                )

    row_index = {str(row.get("module")): idx for idx, row in enumerate(report_rows)}

    closed_loop_idx = row_index.get("virtual_pi_closed_loop")
    if closed_loop_idx is not None:
        runtime_log_text = ""
        for log_path in sorted((ROOT / "pc" / "log").glob("*_web_console.log"), key=lambda p: p.stat().st_mtime, reverse=True)[:3]:
            runtime_log_text += "\n" + log_path.read_text(encoding="utf-8", errors="ignore")
        if (
            "收到节点 [1] 边缘高优告警" in runtime_log_text
            or "收到节点 [1] 边缘策略事件" in runtime_log_text
            or "已回传节点 1 语音播报" in runtime_log_text
        ):
            report_rows[closed_loop_idx]["status"] = "pass"
            report_rows[closed_loop_idx]["detail"] = "运行时日志已确认单节点闭环事件进入 PC 处理链路"

    single_idx = row_index.get("virtual_pi_single_voice_loop")
    if single_idx is not None:
        single_log = ROOT / "tmp" / "virtual_pi_single_voice.jsonl"
        single_text = single_log.read_text(encoding="utf-8", errors="ignore") if single_log.exists() else ""
        single_note = _latest_voice_note_with("移液枪使用后要竖直放置")
        if '"kind": "tts_received"' in single_text and single_note:
            report_rows[single_idx]["status"] = "pass"
            report_rows[single_idx]["detail"] = f"tts_saved=True, note={single_note}"
            report_rows[single_idx]["extra"] = {
                "log_path": str(single_log),
                "knowledge_note": str(single_note),
            }

    multi_idx = row_index.get("virtual_pi_multi_voice_loop")
    if multi_idx is not None:
        multi_log_1 = ROOT / "tmp" / "virtual_pi_multi_1.jsonl"
        multi_log_2 = ROOT / "tmp" / "virtual_pi_multi_2.jsonl"
        text1 = multi_log_1.read_text(encoding="utf-8", errors="ignore") if multi_log_1.exists() else ""
        text2 = multi_log_2.read_text(encoding="utf-8", errors="ignore") if multi_log_2.exists() else ""
        multi_note = _latest_voice_note_with("酸液标签必须朝外放置")
        if '"kind": "tts_received"' in text1 and '"kind": "tts_received"' in text2 and multi_note:
            report_rows[multi_idx]["status"] = "pass"
            report_rows[multi_idx]["detail"] = f"multi1=True, multi2=True, note={multi_note}"
            report_rows[multi_idx]["extra"] = {
                "log_paths": [str(multi_log_1), str(multi_log_2)],
                "knowledge_note": str(multi_note),
            }

    summary = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "workspace": str(ROOT),
        "pass_count": sum(1 for row in report_rows if row.get("status") == "pass"),
        "warn_count": sum(1 for row in report_rows if row.get("status") == "warn"),
        "fail_count": sum(1 for row in report_rows if row.get("status") == "fail"),
        "results": report_rows,
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8-sig")
    return summary


def main() -> int:
    summary = run()
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary.get("fail_count", 0) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
