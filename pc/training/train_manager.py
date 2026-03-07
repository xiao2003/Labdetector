from __future__ import annotations

import json
import threading
import time
import traceback
from pathlib import Path
from typing import Any, Dict

from pc.core.config import get_config
from pc.training.dataset_builder import dataset_builder
from pc.training.dataset_importer import dataset_importer
from pc.training.llm_finetune import run_llm_finetune
from pc.training.model_linker import model_linker
from pc.training.pi_detector_finetune import run_pi_detector_finetune


class TrainingManager:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._jobs: Dict[str, Dict[str, Any]] = {}

    def overview(self) -> Dict[str, Any]:
        with self._lock:
            jobs = list(self._jobs.values())
        return {
            "jobs": jobs,
            "job_count": len(jobs),
            "latest_workspace": self._latest_workspace(),
            "assets": dataset_importer.asset_summary(),
            "deployments": model_linker.deployed_model_summary(),
        }

    def build_training_workspace(self, workspace_name: str = "") -> Dict[str, Any]:
        return dataset_builder.build_training_workspace(workspace_name=workspace_name)

    def import_llm_dataset(self, paths: list[str]) -> Dict[str, Any]:
        return dataset_importer.import_llm_dataset(paths)

    def import_pi_dataset(self, paths: list[str]) -> Dict[str, Any]:
        return dataset_importer.import_pi_dataset(paths)

    def activate_llm_deployment(self, target: str = "") -> Dict[str, Any]:
        return model_linker.activate_llm_deployment(target)

    def activate_pi_deployment(self, target: str = "") -> Dict[str, Any]:
        return model_linker.activate_pi_detector_deployment(target)

    def start_llm_job(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        workspace_dir = Path(str(payload.get("workspace_dir") or "")).expanduser()
        if not workspace_dir.exists():
            raise FileNotFoundError(f"训练工作区不存在: {workspace_dir}")
        output_dir = workspace_dir / "outputs" / "llm_adapter"
        output_dir.mkdir(parents=True, exist_ok=True)
        return self._start_job(
            kind="llm_finetune",
            payload=dict(payload),
            runner=lambda: run_llm_finetune(
                train_path=str(payload.get("train_path") or workspace_dir / "llm_sft" / "train.jsonl"),
                eval_path=str(payload.get("eval_path") or workspace_dir / "llm_sft" / "eval.jsonl"),
                output_dir=str(output_dir),
                base_model=str(payload.get("base_model") or get_config("training.llm_base_model", "")),
                epochs=int(payload.get("epochs") or get_config("training.llm_epochs", 1)),
                batch_size=int(payload.get("batch_size") or get_config("training.llm_batch_size", 1)),
                learning_rate=float(payload.get("learning_rate") or get_config("training.llm_learning_rate", 2e-4)),
                lora_r=int(payload.get("lora_r") or get_config("training.llm_lora_r", 8)),
                lora_alpha=int(payload.get("lora_alpha") or get_config("training.llm_lora_alpha", 16)),
            ),
            postprocess=lambda result: self._postprocess_llm_result(result, workspace_dir, payload),
        )

    def start_pi_job(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        workspace_dir = Path(str(payload.get("workspace_dir") or "")).expanduser()
        if not workspace_dir.exists():
            raise FileNotFoundError(f"训练工作区不存在: {workspace_dir}")
        dataset_yaml = Path(str(payload.get("dataset_yaml") or workspace_dir / "pi_detector" / "dataset.yaml"))
        output_dir = workspace_dir / "outputs" / "pi_detector"
        output_dir.mkdir(parents=True, exist_ok=True)
        return self._start_job(
            kind="pi_detector_finetune",
            payload=dict(payload),
            runner=lambda: run_pi_detector_finetune(
                dataset_yaml=str(dataset_yaml),
                output_dir=str(output_dir),
                base_weights=str(payload.get("base_weights") or get_config("training.pi_base_weights", "yolov8n.pt")),
                epochs=int(payload.get("epochs") or get_config("training.pi_epochs", 20)),
                imgsz=int(payload.get("imgsz") or get_config("training.pi_imgsz", 640)),
                device=str(payload.get("device") or get_config("training.pi_device", "")),
                deploy_to_pi=False,
            ),
            postprocess=lambda result: self._postprocess_pi_result(result, workspace_dir, payload),
        )

    def start_full_pipeline_job(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        workspace_dir = Path(str(payload.get("workspace_dir") or "")).expanduser()
        if not workspace_dir.exists():
            raise FileNotFoundError(f"训练工作区不存在: {workspace_dir}")

        def _runner() -> Dict[str, Any]:
            llm_result = run_llm_finetune(
                train_path=str(payload.get("train_path") or workspace_dir / "llm_sft" / "train.jsonl"),
                eval_path=str(payload.get("eval_path") or workspace_dir / "llm_sft" / "eval.jsonl"),
                output_dir=str(workspace_dir / "outputs" / "llm_adapter"),
                base_model=str(payload.get("base_model") or get_config("training.llm_base_model", "")),
                epochs=int(payload.get("llm_epochs") or get_config("training.llm_epochs", 1)),
                batch_size=int(payload.get("llm_batch_size") or get_config("training.llm_batch_size", 1)),
                learning_rate=float(payload.get("llm_learning_rate") or get_config("training.llm_learning_rate", 2e-4)),
                lora_r=int(payload.get("llm_lora_r") or get_config("training.llm_lora_r", 8)),
                lora_alpha=int(payload.get("llm_lora_alpha") or get_config("training.llm_lora_alpha", 16)),
            )
            pi_result = run_pi_detector_finetune(
                dataset_yaml=str(payload.get("dataset_yaml") or workspace_dir / "pi_detector" / "dataset.yaml"),
                output_dir=str(workspace_dir / "outputs" / "pi_detector"),
                base_weights=str(payload.get("base_weights") or get_config("training.pi_base_weights", "yolov8n.pt")),
                epochs=int(payload.get("pi_epochs") or get_config("training.pi_epochs", 20)),
                imgsz=int(payload.get("pi_imgsz") or get_config("training.pi_imgsz", 640)),
                device=str(payload.get("pi_device") or get_config("training.pi_device", "")),
                deploy_to_pi=False,
            )
            return {"llm": llm_result, "pi": pi_result}

        return self._start_job(
            kind="full_training_pipeline",
            payload=dict(payload),
            runner=_runner,
            postprocess=lambda result: self._postprocess_full_result(result, workspace_dir, payload),
        )

    def _workspace_summary(self, workspace_dir: Path) -> Dict[str, Any]:
        summary_path = workspace_dir / "workspace_summary.json"
        if not summary_path.exists():
            return {}
        try:
            return json.loads(summary_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _postprocess_llm_result(self, result: Dict[str, Any], workspace_dir: Path, payload: Dict[str, Any]) -> Dict[str, Any]:
        deployment = model_linker.register_llm_adapter(
            output_dir=str(result.get("output_dir") or workspace_dir / "outputs" / "llm_adapter"),
            base_model=str(result.get("base_model") or payload.get("base_model") or get_config("training.llm_base_model", "")),
            workspace_dir=str(workspace_dir),
            train_samples=int(result.get("train_samples") or 0),
            eval_samples=int(result.get("eval_samples") or 0),
            activate=bool(payload.get("activate", True)),
            deployment_name=str(payload.get("deployment_name") or workspace_dir.name),
        )
        result = dict(result)
        result["deployment"] = deployment
        return result

    def _postprocess_pi_result(self, result: Dict[str, Any], workspace_dir: Path, payload: Dict[str, Any]) -> Dict[str, Any]:
        workspace_summary = self._workspace_summary(workspace_dir)
        deployment = model_linker.register_pi_detector(
            weights_path=str(result.get("best_weights") or ""),
            workspace_dir=str(workspace_dir),
            sample_count=int(workspace_summary.get("detector_train_samples") or 0),
            class_names=list(workspace_summary.get("detector_class_names") or []),
            conf=float(payload.get("conf") or get_config("pi_detector.conf", 0.4) or 0.4),
            activate=bool(payload.get("activate", True)),
            deployment_name=str(payload.get("deployment_name") or workspace_dir.name),
        )
        result = dict(result)
        result["deployment"] = deployment
        return result

    def _postprocess_full_result(self, result: Dict[str, Any], workspace_dir: Path, payload: Dict[str, Any]) -> Dict[str, Any]:
        combined = dict(result)
        llm_result = self._postprocess_llm_result(dict(combined.get("llm") or {}), workspace_dir, payload)
        pi_result = self._postprocess_pi_result(dict(combined.get("pi") or {}), workspace_dir, payload)
        combined["llm"] = llm_result
        combined["pi"] = pi_result
        combined["deployments"] = {
            "llm": llm_result.get("deployment", {}),
            "pi": pi_result.get("deployment", {}),
        }
        return combined

    def _start_job(self, *, kind: str, payload: Dict[str, Any], runner, postprocess=None) -> Dict[str, Any]:
        job_id = f"{kind}_{time.strftime('%Y%m%d_%H%M%S')}"
        job = {
            "job_id": job_id,
            "kind": kind,
            "status": "running",
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "payload": payload,
            "result": None,
            "error": "",
        }
        with self._lock:
            self._jobs[job_id] = job

        def _worker() -> None:
            try:
                result = runner()
                if postprocess is not None:
                    result = postprocess(result)
                with self._lock:
                    job["status"] = "finished"
                    job["result"] = result
            except Exception as exc:
                with self._lock:
                    job["status"] = "failed"
                    job["error"] = f"{exc}\n{traceback.format_exc()}"

        threading.Thread(target=_worker, daemon=True, name=job_id).start()
        return job

    def _latest_workspace(self) -> str:
        root = dataset_builder.training_root
        if not root.exists():
            return ""
        dirs = [path for path in root.iterdir() if path.is_dir()]
        if not dirs:
            return ""
        return str(sorted(dirs)[-1])


training_manager = TrainingManager()
