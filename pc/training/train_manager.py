from __future__ import annotations

import json
import subprocess
import threading
import time
import traceback
from pathlib import Path
from typing import Any, Dict

from pc.core.config import get_config
from pc.training.dataset_builder import dataset_builder
from pc.training.dataset_importer import dataset_importer
from pc.training.model_linker import model_linker
from pc.training.runtime_env import (
    build_training_python_env,
    describe_training_python,
    resolve_training_python_executable,
    training_worker_script_path,
)


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
            "runtime_python": describe_training_python(),
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
        llm_payload = {
            "train_path": str(payload.get("train_path") or workspace_dir / "llm_sft" / "train.jsonl"),
            "eval_path": str(payload.get("eval_path") or workspace_dir / "llm_sft" / "eval.jsonl"),
            "output_dir": str(output_dir),
            "base_model": str(payload.get("base_model") or get_config("training.llm_base_model", "")),
            "epochs": int(payload.get("epochs") or get_config("training.llm_epochs", 1)),
            "batch_size": int(payload.get("batch_size") or get_config("training.llm_batch_size", 1)),
            "learning_rate": float(payload.get("learning_rate") or get_config("training.llm_learning_rate", 2e-4)),
            "lora_r": int(payload.get("lora_r") or get_config("training.llm_lora_r", 8)),
            "lora_alpha": int(payload.get("lora_alpha") or get_config("training.llm_lora_alpha", 16)),
        }
        return self._start_job(
            kind="llm_finetune",
            payload=dict(payload),
            runner=lambda: self._run_worker("llm", workspace_dir, llm_payload),
            postprocess=lambda result: self._postprocess_llm_result(result, workspace_dir, payload),
        )

    def start_pi_job(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        workspace_dir = Path(str(payload.get("workspace_dir") or "")).expanduser()
        if not workspace_dir.exists():
            raise FileNotFoundError(f"训练工作区不存在: {workspace_dir}")
        dataset_yaml = Path(str(payload.get("dataset_yaml") or workspace_dir / "pi_detector" / "dataset.yaml"))
        output_dir = workspace_dir / "outputs" / "pi_detector"
        output_dir.mkdir(parents=True, exist_ok=True)
        pi_payload = {
            "dataset_yaml": str(dataset_yaml),
            "output_dir": str(output_dir),
            "base_weights": str(payload.get("base_weights") or get_config("training.pi_base_weights", "yolov8n.pt")),
            "epochs": int(payload.get("epochs") or get_config("training.pi_epochs", 20)),
            "imgsz": int(payload.get("imgsz") or get_config("training.pi_imgsz", 640)),
            "device": str(payload.get("device") or get_config("training.pi_device", "")),
            "deploy_to_pi": False,
        }
        return self._start_job(
            kind="pi_detector_finetune",
            payload=dict(payload),
            runner=lambda: self._run_worker("pi", workspace_dir, pi_payload),
            postprocess=lambda result: self._postprocess_pi_result(result, workspace_dir, payload),
        )

    def start_full_pipeline_job(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        workspace_dir = Path(str(payload.get("workspace_dir") or "")).expanduser()
        if not workspace_dir.exists():
            raise FileNotFoundError(f"训练工作区不存在: {workspace_dir}")

        def _runner() -> Dict[str, Any]:
            llm_payload = {
                "train_path": str(payload.get("train_path") or workspace_dir / "llm_sft" / "train.jsonl"),
                "eval_path": str(payload.get("eval_path") or workspace_dir / "llm_sft" / "eval.jsonl"),
                "output_dir": str(workspace_dir / "outputs" / "llm_adapter"),
                "base_model": str(payload.get("base_model") or get_config("training.llm_base_model", "")),
                "epochs": int(payload.get("llm_epochs") or get_config("training.llm_epochs", 1)),
                "batch_size": int(payload.get("llm_batch_size") or get_config("training.llm_batch_size", 1)),
                "learning_rate": float(payload.get("llm_learning_rate") or get_config("training.llm_learning_rate", 2e-4)),
                "lora_r": int(payload.get("llm_lora_r") or get_config("training.llm_lora_r", 8)),
                "lora_alpha": int(payload.get("llm_lora_alpha") or get_config("training.llm_lora_alpha", 16)),
            }
            pi_payload = {
                "dataset_yaml": str(payload.get("dataset_yaml") or workspace_dir / "pi_detector" / "dataset.yaml"),
                "output_dir": str(workspace_dir / "outputs" / "pi_detector"),
                "base_weights": str(payload.get("base_weights") or get_config("training.pi_base_weights", "yolov8n.pt")),
                "epochs": int(payload.get("pi_epochs") or get_config("training.pi_epochs", 20)),
                "imgsz": int(payload.get("pi_imgsz") or get_config("training.pi_imgsz", 640)),
                "device": str(payload.get("pi_device") or get_config("training.pi_device", "")),
                "deploy_to_pi": False,
            }
            llm_result = self._run_worker("llm", workspace_dir, llm_payload)
            pi_result = self._run_worker("pi", workspace_dir, pi_payload)
            return {"llm": llm_result, "pi": pi_result}

        return self._start_job(
            kind="full_training_pipeline",
            payload=dict(payload),
            runner=_runner,
            postprocess=lambda result: self._postprocess_full_result(result, workspace_dir, payload),
        )

    def _decode_subprocess_output(self, payload: bytes) -> str:
        for encoding in ("utf-8", "gbk", "cp936"):
            try:
                return payload.decode(encoding)
            except Exception:
                continue
        return payload.decode("utf-8", errors="ignore")

    def _run_worker(self, worker_kind: str, workspace_dir: Path, payload: Dict[str, Any]) -> Dict[str, Any]:
        python_exe = resolve_training_python_executable()
        if python_exe is None:
            raise RuntimeError("未找到训练运行时 Python，请先执行启动自检或重新构建发布包。")

        worker_path = training_worker_script_path()
        if not worker_path.exists():
            raise FileNotFoundError(f"训练工作进程脚本不存在: {worker_path}")

        runtime_root = workspace_dir / "outputs" / ".job_runtime"
        runtime_root.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        payload_path = runtime_root / f"{worker_kind}_{stamp}_payload.json"
        result_path = runtime_root / f"{worker_kind}_{stamp}_result.json"
        log_path = runtime_root / f"{worker_kind}_{stamp}.log"
        payload_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        command = [
            str(python_exe),
            str(worker_path),
            "--kind",
            worker_kind,
            "--payload-json",
            str(payload_path),
            "--result-json",
            str(result_path),
        ]
        proc = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=build_training_python_env(python_exe),
            cwd=str(workspace_dir),
        )
        output = self._decode_subprocess_output(proc.stdout)
        log_path.write_text(output or "", encoding="utf-8")

        result_payload: Dict[str, Any] = {}
        if result_path.exists():
            try:
                result_payload = json.loads(result_path.read_text(encoding="utf-8"))
            except Exception:
                result_payload = {}

        if proc.returncode != 0 or not bool(result_payload.get("ok", False)):
            error_message = str(result_payload.get("error") or "训练子进程执行失败").strip()
            trace_text = str(result_payload.get("traceback") or "").strip()
            detail = f"{error_message}。日志: {log_path}"
            if trace_text:
                detail = f"{detail}\n{trace_text}"
            raise RuntimeError(detail)

        result = dict(result_payload.get("result") or {})
        result["log_path"] = str(log_path)
        result["runner_python"] = str(python_exe)
        return result

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
