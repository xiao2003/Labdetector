from __future__ import annotations

import threading
import time
import traceback
from pathlib import Path
from typing import Any, Dict

from pc.core.config import get_config
from pc.training.dataset_builder import dataset_builder
from pc.training.llm_finetune import run_llm_finetune
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
        }

    def build_training_workspace(self, workspace_name: str = "") -> Dict[str, Any]:
        return dataset_builder.build_training_workspace(workspace_name=workspace_name)

    def start_llm_job(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        workspace_dir = Path(str(payload.get("workspace_dir") or "")).expanduser()
        if not workspace_dir.exists():
            raise FileNotFoundError(f"????????: {workspace_dir}")
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
        )

    def start_pi_job(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        workspace_dir = Path(str(payload.get("workspace_dir") or "")).expanduser()
        if not workspace_dir.exists():
            raise FileNotFoundError(f"????????: {workspace_dir}")
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
                deploy_to_pi=bool(payload.get("deploy_to_pi", True)),
            ),
        )

    def _start_job(self, *, kind: str, payload: Dict[str, Any], runner) -> Dict[str, Any]:
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
