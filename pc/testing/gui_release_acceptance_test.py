from __future__ import annotations

import argparse
import json
import threading
import time
import tempfile
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import patch

from pc.core.config import get_config, set_config
from pc.testing.gui_full_closed_loop_test import SilentDialogRecorder, _collect_window_state, _set_entry, _wait_for
from pc.testing.virtual_text_voice_closed_loop_test import VirtualAudioVoicePiServer
from pc.training.model_linker import model_linker
from pc.training.train_manager import training_manager


def _count_nonempty_lines(path: Path) -> int:
    if not path.exists():
        return 0
    return len([line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()])


def _count_child_dirs(path: Path) -> int:
    if not path.exists():
        return 0
    return len([item for item in path.iterdir() if item.is_dir()])


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="执行 GUI 发布验收闭环测试")
    parser.add_argument(
        "--report-file",
        default=str(Path("release/gui_release_acceptance_report.json")),
        help="测试报告输出路径",
    )
    parser.add_argument(
        "--node-count",
        type=int,
        default=1,
        help="虚拟 Pi 节点数量，仅支持 1 或 4。",
    )
    return parser.parse_args()


def _prepare_release_assets(asset_root: Path) -> Dict[str, str]:
    asset_root.mkdir(parents=True, exist_ok=True)
    knowledge_root = asset_root / "knowledge"
    knowledge_root.mkdir(parents=True, exist_ok=True)
    expert_asset_root = asset_root / "expert_assets"
    expert_asset_root.mkdir(parents=True, exist_ok=True)

    common_doc = knowledge_root / "common_lab_guide.txt"
    common_doc.write_text(
        "实验室系统状态问答应优先返回当前监控状态、在线节点数量和最近一次专家结果。\n"
        "如果用户询问系统状态，应说明监控链路、知识库和训练工作台是否可用。\n",
        encoding="utf-8",
    )
    chem_doc = knowledge_root / "chem_release_test.txt"
    chem_doc.write_text(
        "HF 属于高风险危化品，若未佩戴手套和护目镜，应立即停止操作并上报。\n",
        encoding="utf-8",
    )
    ppe_doc = knowledge_root / "ppe_release_test.txt"
    ppe_doc.write_text(
        "进入实验区必须穿实验服、佩戴手套和护目镜。发现 PPE 不完整时应立即整改。\n",
        encoding="utf-8",
    )
    llm_doc = asset_root / "llm_release_train.txt"
    llm_doc.write_text(
        "问: 介绍当前系统状态\n答: 当前系统运行正常，监控、知识库和训练工作台均已就绪。\n\n"
        "问: 分析当前实验风险并给出处置建议\n答: 请先确认危化品暴露、PPE 完整性和现场隔离措施，再继续实验。\n",
        encoding="utf-8",
    )

    chem_model = expert_asset_root / "chem_expert_weights.bin"
    chem_model.write_bytes(b"chem-expert-release-test")
    ppe_model = expert_asset_root / "ppe_expert_weights.bin"
    ppe_model.write_bytes(b"ppe-expert-release-test")

    return {
        "asset_root": str(asset_root),
        "common_doc": str(common_doc),
        "chem_doc": str(chem_doc),
        "ppe_doc": str(ppe_doc),
        "llm_doc": str(llm_doc),
        "chem_model": str(chem_model),
        "ppe_model": str(ppe_model),
    }


def _server_plan(node_count: int) -> List[VirtualAudioVoicePiServer]:
    voice_plans = [
        ["wake_word", "dynamic_qa_status", "wake_word", "fixed_model_risk"],
        ["wake_word", "fixed_expert_hf", "wake_word", "dynamic_qa_status"],
        ["wake_word", "dynamic_model_risk", "wake_word", "fixed_qa_status"],
        ["wake_word", "fixed_model_risk", "wake_word", "dynamic_expert_ppe"],
    ]
    visual_events = ["危化品识别", "PPE穿戴检查", "危化品识别", "PPE穿戴检查"]
    total = 1 if node_count == 1 else 4
    servers: List[VirtualAudioVoicePiServer] = []
    for index in range(total):
        servers.append(
            VirtualAudioVoicePiServer(
                port=8771 + index,
                node_id=str(index + 1),
                voice_sample_keys=voice_plans[index],
                visual_event_name=visual_events[index],
            )
        )
    return servers


def _fake_training_worker(worker_kind: str, workspace_dir: Path, payload: Dict[str, Any]) -> Dict[str, Any]:
    output_root = workspace_dir / "outputs"
    output_root.mkdir(parents=True, exist_ok=True)
    if worker_kind == "llm":
        output_dir = Path(str(payload["output_dir"]))
        output_dir.mkdir(parents=True, exist_ok=True)
        adapter_path = output_dir / "adapter_model.bin"
        adapter_path.write_bytes(b"llm-adapter-release-test")
        summary = {
            "output_dir": str(output_dir),
            "train_samples": 2,
            "eval_samples": 0,
            "base_model": str(payload.get("base_model") or "gemma3:4b"),
            "epochs": 1,
            "batch_size": 1,
            "learning_rate": 2e-4,
            "lora_r": 8,
            "lora_alpha": 16,
        }
        (output_dir / "training_result.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        return summary
    if worker_kind == "pi":
        output_dir = Path(str(payload["output_dir"])) / "run"
        weights_dir = output_dir / "weights"
        weights_dir.mkdir(parents=True, exist_ok=True)
        best_path = weights_dir / "best.pt"
        best_path.write_bytes(b"pi-detector-release-test")
        summary = {
            "output_dir": str(output_dir),
            "best_weights": str(best_path),
            "deployed_path": "",
            "results": "release-test",
            "epochs": 1,
            "imgsz": 640,
            "base_weights": str(payload.get("base_weights") or "yolov8n.pt"),
            "dataset_yaml": str(payload.get("dataset_yaml") or ""),
        }
        (output_dir / "training_result.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        return summary
    raise ValueError(f"未知训练任务类型: {worker_kind}")


def run_gui_release_acceptance_test(report_file: str, *, node_count: int) -> Dict[str, Any]:
    if node_count not in {1, 4}:
        raise ValueError("仅支持 1 节点或 4 节点发布验收。")

    from pc.core.expert_manager import expert_manager
    from pc.desktop_app import DesktopApp

    report_path = Path(report_file).resolve()
    asset_root = report_path.parent / "gui_release_acceptance_assets" / time.strftime("%Y%m%d_%H%M%S")
    orchestrator_test_root = Path(tempfile.mkdtemp(prefix="neurolab_orchestrator_acceptance_"))
    orchestrator_state_file = orchestrator_test_root / "state.json"
    orchestrator_model_root = orchestrator_test_root / "models"
    orchestrator_download_root = orchestrator_test_root / "downloads"
    assets = _prepare_release_assets(asset_root)
    servers = _server_plan(node_count)
    dialog_recorder = SilentDialogRecorder()

    endpoints = ",".join(server.endpoint() for server in servers)
    preserved_config = {
        "network.virtual_pi_enabled": get_config("network.virtual_pi_enabled", False),
        "network.virtual_pi_host": get_config("network.virtual_pi_host", "127.0.0.1"),
        "network.virtual_pi_hosts": get_config("network.virtual_pi_hosts", ""),
        "session_defaults.project_name": get_config("session_defaults.project_name", ""),
        "session_defaults.experiment_name": get_config("session_defaults.experiment_name", ""),
        "session_defaults.operator_name": get_config("session_defaults.operator_name", ""),
        "session_defaults.tags": get_config("session_defaults.tags", ""),
    }

    report: Dict[str, Any] = {
        "success": False,
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "report_file": str(report_path),
        "node_count": node_count,
        "assets": assets,
        "steps": [],
        "dialogs": [],
        "windows": {},
        "model_selection": {},
        "knowledge": {},
        "experts": {},
        "training": {},
        "archive": {},
        "session": {},
        "servers": [],
        "errors": [],
    }

    app = None

    def pump() -> None:
        if app is None:
            return
        app.root.update_idletasks()
        app.root.update()

    def add_step(name: str, **payload: Any) -> None:
        row = {"name": name, "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")}
        row.update(payload)
        report["steps"].append(row)

    def endpoint_map(_expected_nodes: int) -> Dict[str, str]:
        return {str(index + 1): servers[index].endpoint() for index in range(len(servers))}

    try:
        for server in servers:
            server.start()
        set_config("network.virtual_pi_enabled", True)
        set_config("network.virtual_pi_host", servers[0].endpoint())
        set_config("network.virtual_pi_hosts", endpoints)

        initial_job_ids = {
            str(job.get("job_id") or "")
            for job in training_manager.overview().get("jobs", [])
            if str(job.get("job_id") or "")
        }
        initial_llm_deployment_ids = {
            str(row.get("deployment_id") or "")
            for row in model_linker.list_llm_deployments()
            if str(row.get("deployment_id") or "")
        }
        initial_pi_deployment_ids = {
            str(row.get("deployment_id") or "")
            for row in model_linker.list_pi_detector_deployments()
            if str(row.get("deployment_id") or "")
        }

        with dialog_recorder, patch.object(expert_manager, "_build_knowledge_context", lambda *args, **kwargs: {}), patch.object(
            expert_manager,
            "_run_llm_interpreter",
            lambda _expert, _frame, _context, raw_response: raw_response,
        ), patch.object(
            expert_manager,
            "route_and_analyze",
            lambda event_name, frame, context, allowed_expert_codes=None, trigger_mode=None: "极度危险：识别到 HF 且未检测到手套，请立即停止操作并上报。"
            if event_name == "危化品识别"
            else "PPE 规范提醒：检测到人员但未完整佩戴实验服、手套和护目镜。",
        ), patch("pc.core.orchestrator.ask_assistant_with_rag", lambda frame, question, rag_context, model_name: f"离线答复：已收到指令“{question}”，当前系统运行正常。"), patch(
            "pc.communication.network_scanner.scan_multi_nodes",
            endpoint_map,
        ), patch(
            "pc.core.orchestrator_runtime.orchestrator_state_path",
            lambda: orchestrator_state_file,
        ), patch(
            "pc.core.orchestrator_runtime.orchestrator_model_dir",
            lambda: orchestrator_model_root,
        ), patch(
            "pc.core.orchestrator_runtime.orchestrator_download_dir",
            lambda: orchestrator_download_root,
        ), patch.object(training_manager, "_run_worker", _fake_training_worker):
            app = DesktopApp()
            app.root.withdraw()
            if app.splash is not None and app.splash.winfo_exists():
                app.splash.withdraw()

            _wait_for(
                pump,
                lambda: app.runtime is not None and bool(app.backend_map) and bool(app.current_state.get("summary")) and bool(app.current_state.get("orchestrator")),
                timeout=80,
                message="GUI 启动基础状态未就绪",
            )
            allowed_bootstrap_states = {"系统已可用", "后台准备中", "后台准备失败（已回退规则链）"}
            if str(app.hero_var.get()).strip() not in allowed_bootstrap_states:
                raise AssertionError(f"首屏状态未收敛到产品化三态: {app.hero_var.get()!r}")
            app.runtime._configure_backend = lambda: None
            app.runtime._start_background_aux_services = lambda **kwargs: None
            app.runtime._ensure_training_dependencies_ready = lambda: None
            add_step("bootstrap_ready", planner_backend=app.current_state.get("orchestrator", {}).get("planner_backend", ""), orchestrator_status=app.current_state.get("orchestrator", {}).get("status", ""))

            app._show_manual_window()
            app._show_cloud_backend_window()
            app._show_knowledge_base_window()
            app._show_expert_window()
            app._show_training_window()
            app._show_archive_window()
            _wait_for(
                pump,
                lambda: all(
                    [
                        app.kb_window is not None and app.kb_window.winfo_exists(),
                        app.expert_window is not None and app.expert_window.winfo_exists(),
                        app.archive_window is not None and app.archive_window.winfo_exists(),
                        app.training_window is not None and app.training_window.winfo_exists(),
                        app.cloud_window is not None and app.cloud_window.winfo_exists(),
                    ]
                ),
                timeout=10,
                message="GUI 模块窗口未全部打开",
            )
            report["windows"] = _collect_window_state(app)
            add_step("windows_opened", **report["windows"])
            app._show_about_window()
            _wait_for(
                pump,
                lambda: app.about_window is not None and app.about_window.winfo_exists(),
                timeout=10,
                message="关于系统窗口未打开",
            )
            if app.copyright_window is not None and app.copyright_window.winfo_exists():
                raise AssertionError("关于系统仍会额外弹出版权窗口")
            if str(app.priority_event_detail_var.get()).strip():
                raise AssertionError("默认高优事项仍保留了额外详情文本")
            if app.priority_event_detail_label is not None:
                raise AssertionError("高优事项详情标签未被移除")
            if app.log_detail_panel is not None:
                raise AssertionError("事件详情栏未移除")

            app._run_self_check()
            _wait_for(
                pump,
                lambda: len(app.current_state.get("self_check", [])) >= 5,
                timeout=30,
                message="主界面自检结果未刷新",
            )
            _wait_for(
                pump,
                lambda: any(
                    str(row.get("category") or "") == "任务进度"
                    and "本机任务" in str(row.get("summary") or "")
                    and "[" in str(row.get("summary") or "")
                    for row in list(app.log_rows)
                ),
                timeout=10,
                message="本机任务进度日志未写入主界面",
            )
            add_step("self_check_completed", items=len(app.current_state.get("self_check", [])))

            app.backend_combo.set(app.backend_reverse["ollama"])
            app.custom_model_registry["ollama"] = [{"name": "gemma3:4b-release", "model": "gemma3:4b"}]
            app._save_custom_model_registry()
            app._update_model_choices(selected_model="gemma3:4b-release")
            app.model_combo.set("gemma3:4b-release")
            app._handle_model_selection()
            report["model_selection"] = {
                "backend": app.backend_combo.get(),
                "selected_model": app.model_combo.get(),
                "available_models": list(app.model_combo.cget("values"))[:12],
            }
            available_models = set(str(item) for item in app.model_combo.cget("values"))
            required_models = {"qwen3.5:4b", "qwen3.5:9b", "qwen3.5:27b", "qwen3.5:35b"}
            missing_models = sorted(required_models - available_models)
            if missing_models:
                raise AssertionError(f"Ollama 默认候选缺失: {missing_models}")
            add_step("model_selected", selected_model=app.model_combo.get())

            with patch("tkinter.filedialog.askopenfilenames", return_value=[assets["common_doc"]]):
                app._import_knowledge_files("common")
            _wait_for(
                pump,
                lambda: any(row.get("scope") == "common" and int(row.get("doc_count", 0) or 0) >= 1 for row in app.knowledge_catalog),
                timeout=90,
                message="公共知识导入未完成",
            )
            _wait_for(
                pump,
                lambda: "最近一次导入" in str(app.kb_status_var.get()) and "新增文档" in str(app.kb_status_var.get()),
                timeout=20,
                message="知识导入业务反馈未更新",
            )

            app.expert_tree.selection_set("safety.chem_safety_expert")
            app._on_expert_tree_select()
            with patch("tkinter.filedialog.askopenfilenames", return_value=[assets["chem_model"]]):
                app._import_selected_expert_assets(False)
            _wait_for(
                pump,
                lambda: any(row.get("expert_code") == "safety.chem_safety_expert" and row.get("asset_ready") for row in app.expert_catalog),
                timeout=20,
                message="危化品专家模型资产导入未完成",
            )
            app.expert_tree.selection_set("safety.chem_safety_expert")
            app._on_expert_tree_select()
            with patch("tkinter.filedialog.askopenfilenames", return_value=[assets["chem_doc"]]):
                app._import_selected_expert_knowledge_text()
            _wait_for(
                pump,
                lambda: any(
                    row.get("scope") == "expert.safety.chem_safety_expert"
                    and any("chem_release_test" in str(name) for name in list(row.get("docs") or []))
                    for row in app.knowledge_catalog
                ),
                timeout=90,
                message="危化品专家知识导入未完成",
            )

            app.expert_tree.selection_set("safety.ppe_expert")
            app._on_expert_tree_select()
            with patch("tkinter.filedialog.askopenfilenames", return_value=[assets["ppe_model"]]):
                app._import_selected_expert_assets(False)
            _wait_for(
                pump,
                lambda: any(row.get("expert_code") == "safety.ppe_expert" and row.get("asset_ready") for row in app.expert_catalog),
                timeout=20,
                message="PPE 专家模型资产导入未完成",
            )
            app.expert_tree.selection_set("safety.ppe_expert")
            app._on_expert_tree_select()
            with patch("tkinter.filedialog.askopenfilenames", return_value=[assets["ppe_doc"]]):
                app._import_selected_expert_knowledge_text()
            _wait_for(
                pump,
                lambda: any(
                    row.get("scope") == "expert.safety.ppe_expert"
                    and any("ppe_release_test" in str(name) for name in list(row.get("docs") or []))
                    for row in app.knowledge_catalog
                ),
                timeout=90,
                message="PPE 专家知识导入未完成",
            )

            report["knowledge"] = {
                "scope_count": len(app.knowledge_catalog),
                "scopes": [row["scope"] for row in app.knowledge_catalog[:16]],
            }
            report["experts"] = {
                "expert_count": len(app.expert_catalog),
                "focus_experts": [
                    row
                    for row in app.expert_catalog
                    if row.get("expert_code") in {"safety.chem_safety_expert", "safety.ppe_expert"}
                ],
            }
            add_step("knowledge_and_experts_ready", scope_count=report["knowledge"]["scope_count"], expert_count=report["experts"]["expert_count"])

            app._handle_voice_local_command("打开知识中心", "open_knowledge_center")
            _wait_for(
                pump,
                lambda: any("管家已执行动作: open_view -> 已切换到知识中心" in str(row.get("detail") or "") for row in list(app.log_rows)),
                timeout=15,
                message="自治动作结果日志未写入事件流",
            )

            app.runtime._log_raw_line("[WARN] 高危告警：检测到 HF 泄漏，请立即停止操作。", level="WARN")
            app._render_logs(app.runtime.get_state().get("logs", []))
            _wait_for(
                pump,
                lambda: "高优先级事项" in str(app.priority_event_title_var.get()) and "HF 泄漏" in str(app.priority_event_title_var.get()),
                timeout=10,
                message="高优事件头部卡片未更新",
            )

            workspace_name = f"gui_release_acceptance_{time.strftime('%Y%m%d_%H%M%S')}"
            _set_entry(app.training_workspace_entry, workspace_name)
            _set_entry(app.training_base_model_entry, "gemma3:4b")
            _set_entry(app.training_pi_weights_entry, "yolov8n.pt")
            app._build_training_workspace_from_form()
            _wait_for(
                pump,
                lambda: bool((app.training_overview or {}).get("latest_workspace"))
                or bool(training_manager.overview().get("latest_workspace")),
                timeout=30,
                message="训练工作区未生成",
            )
            latest_workspace = str(training_manager.overview().get("latest_workspace") or "")
            if latest_workspace and latest_workspace != str((app.training_overview or {}).get("latest_workspace") or ""):
                app.training_overview = app.runtime.get_training_overview()
                app._render_training_overview()

            training_assets_root = Path(__file__).resolve().parents[1] / "training_assets"
            llm_records_path = training_assets_root / "llm" / "records.jsonl"
            initial_llm_mtime = llm_records_path.stat().st_mtime if llm_records_path.exists() else 0.0
            with patch.object(app, "_pick_paths_for_import", return_value=[assets["llm_doc"]]):
                app._import_llm_dataset_from_dialog()
            _wait_for(
                pump,
                lambda: llm_records_path.exists() and llm_records_path.stat().st_mtime >= initial_llm_mtime,
                timeout=60,
                message="LLM 训练数据未导入完成",
            )

            app._generate_training_annotation_samples()
            _wait_for(
                pump,
                lambda: len(app.training_annotation_items) >= 3,
                timeout=20,
                message="测试标注图片未生成",
            )
            first_image = app.training_annotation_items[0]["name"]
            app.training_annotation_tree.selection_set(first_image)
            app._on_training_annotation_select()
            _wait_for(
                pump,
                lambda: bool(app.training_annotation_current_item),
                timeout=10,
                message="标注图片未载入",
            )
            app.training_annotation_class_entry.delete(0, "end")
            app.training_annotation_class_entry.insert(0, "hazard_box")
            app._on_training_annotation_press(type("Evt", (), {"x": 120, "y": 120})())
            app._on_training_annotation_drag(type("Evt", (), {"x": 300, "y": 260})())
            app._on_training_annotation_release(type("Evt", (), {"x": 300, "y": 260})())
            app._save_training_annotations()
            workspace_dir = str((app.training_overview or {}).get("latest_workspace") or latest_workspace or "")
            label_path = Path(workspace_dir) / "pi_detector" / "labels" / "train" / f"{Path(first_image).stem}.txt"
            _wait_for(
                pump,
                lambda: label_path.exists() and bool(label_path.read_text(encoding="utf-8").strip()),
                timeout=15,
                message="标注结果未写入标签文件",
            )
            pi_dataset_root = training_assets_root / "pi_detector" / "datasets"
            initial_pi_datasets = _count_child_dirs(pi_dataset_root)
            with patch.object(app, "_pick_paths_for_import", return_value=[str(Path(workspace_dir) / "pi_detector")]):
                app._import_pi_dataset_from_dialog()
            _wait_for(
                pump,
                lambda: _count_child_dirs(pi_dataset_root) > initial_pi_datasets,
                timeout=30,
                message="Pi 数据集导入未完成",
            )

            app._start_llm_training_from_form()
            app._start_pi_training_from_form()

            def _new_training_jobs() -> list[dict[str, Any]]:
                jobs = training_manager.overview().get("jobs", [])
                return [
                    job
                    for job in jobs
                    if str(job.get("job_id") or "") and str(job.get("job_id") or "") not in initial_job_ids
                ]

            llm_output_file = Path(workspace_dir) / "outputs" / "llm_adapter" / "adapter_model.bin"
            pi_output_file = Path(workspace_dir) / "outputs" / "pi_detector" / "run" / "weights" / "best.pt"

            def _new_training_deployments_ready() -> bool:
                llm_rows = [
                    row
                    for row in model_linker.list_llm_deployments()
                    if str(row.get("deployment_id") or "") not in initial_llm_deployment_ids
                    and str(row.get("workspace_dir") or "") == workspace_dir
                ]
                pi_rows = [
                    row
                    for row in model_linker.list_pi_detector_deployments()
                    if str(row.get("deployment_id") or "") not in initial_pi_deployment_ids
                    and str(row.get("workspace_dir") or "") == workspace_dir
                ]
                return bool(llm_rows) and bool(pi_rows)

            _wait_for(
                pump,
                lambda: llm_output_file.exists() and pi_output_file.exists() and _new_training_deployments_ready(),
                timeout=150,
                message="训练产物或部署结果未生成",
            )
            failed_jobs = [
                job
                for job in _new_training_jobs()
                if str(job.get("status") or "") == "failed"
            ]
            if failed_jobs:
                raise AssertionError(f"训练任务执行失败: {[job.get('job_id') for job in failed_jobs]}")
            training_jobs = _new_training_jobs()
            llm_deployments = [
                row
                for row in model_linker.list_llm_deployments()
                if str(row.get("deployment_id") or "") not in initial_llm_deployment_ids
                and str(row.get("workspace_dir") or "") == workspace_dir
            ]
            pi_deployments = [
                row
                for row in model_linker.list_pi_detector_deployments()
                if str(row.get("deployment_id") or "") not in initial_pi_deployment_ids
                and str(row.get("workspace_dir") or "") == workspace_dir
            ]
            report["training"] = {
                "workspace_dir": workspace_dir,
                "annotation_image_count": len(app.training_annotation_items),
                "annotation_label_path": str(label_path),
                "training_status": str(app.training_status_var.get()),
                "overview": dict(app.training_overview or {}),
                "jobs": training_jobs,
                "llm_output_file": str(llm_output_file),
                "pi_output_file": str(pi_output_file),
                "llm_deployments": llm_deployments,
                "pi_deployments": pi_deployments,
            }
            add_step(
                "training_ready",
                job_count=len(training_jobs),
                llm_deployment_count=len(llm_deployments),
                pi_deployment_count=len(pi_deployments),
                workspace_dir=workspace_dir,
            )

            app.mode_combo.set(app.mode_reverse["websocket"])
            _set_entry(app.expected_entry, str(node_count))
            if app.project_entry is not None:
                _set_entry(app.project_entry, "GUI 发布验收测试")
            if app.experiment_entry is not None:
                _set_entry(app.experiment_entry, f"{node_count} 节点虚拟部署")
            if app.operator_entry is not None:
                _set_entry(app.operator_entry, "Codex")
            if app.tags_entry is not None:
                _set_entry(app.tags_entry, f"GUI,发布验收,{node_count}节点")
            app._sync_field_visibility()
            app._start_session()
            _wait_for(
                pump,
                lambda: str(app.current_state.get("session", {}).get("phase") or "") == "running"
                and int(app.current_state.get("summary", {}).get("online_nodes", 0) or 0) >= node_count,
                timeout=50,
                message="监控会话未成功启动或节点未全部上线",
            )
            app.runtime.request_remote_self_checks()
            _wait_for(
                pump,
                lambda: any(
                    str(row.get("category") or "") == "任务进度"
                    and "节点 " in str(row.get("summary") or "")
                    and "[" in str(row.get("summary") or "")
                    for row in list(app.log_rows)
                ),
                timeout=20,
                message="节点任务进度日志未回传到主界面",
            )
            _wait_for(
                pump,
                lambda: all(len(server.received_tts) >= 2 and len(server.received_expert_results) >= 1 and len(server.acks) >= 1 for server in servers),
                timeout=80,
                message="PC-Pi 音频/视觉闭环未全部完成",
            )
            summary = dict(app.current_state.get("summary", {}))
            online_nodes = int(summary.get("online_nodes", 0) or 0)
            offline_nodes = int(summary.get("offline_nodes", 0) or 0)
            expected_offline = max(0, node_count - online_nodes)
            if offline_nodes != expected_offline:
                raise AssertionError(f"离线节点数不符合预期: expected={expected_offline}, actual={offline_nodes}")
            app._stop_session()
            _wait_for(
                pump,
                lambda: str(app.current_state.get("session", {}).get("phase") or "") == "idle",
                timeout=20,
                message="监控会话未停止",
            )
            app._refresh_archive_catalog()
            _wait_for(
                pump,
                lambda: len(app.archive_catalog) > 0,
                timeout=20,
                message="实验档案未刷新",
            )

            report["archive"] = {
                "archive_count": len(app.archive_catalog),
                "latest": app.archive_catalog[0] if app.archive_catalog else {},
            }
            report["session"] = {
                "summary": summary,
                "session": dict(app.current_state.get("session", {})),
            }
            report["servers"] = [
                {
                    "endpoint": server.endpoint(),
                    "node_id": server.node_id,
                    "voice_commands": list(server.sent_voice_commands),
                    "audio_records": list(server.audio_records),
                    "received_tts": list(server.received_tts),
                    "received_expert_results": list(server.received_expert_results),
                    "acks": list(server.acks),
                    "received_commands": list(server.received_commands),
                }
                for server in servers
            ]
            add_step("pc_pi_closed_loop_completed", online_nodes=online_nodes, node_count=node_count, archive_count=len(app.archive_catalog))

        report["dialogs"] = list(dialog_recorder.records)
        report["success"] = True
        report["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        return report
    except Exception as exc:
        report["errors"].append(str(exc))
        report["dialogs"] = list(dialog_recorder.records)
        report["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        return report
    finally:
        for key, value in preserved_config.items():
            set_config(key, value)
        if app is not None:
            try:
                app._on_close()
            except Exception:
                pass
        for server in servers:
            server.stop()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    args = _parse_args()
    report = run_gui_release_acceptance_test(args.report_file, node_count=args.node_count)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
