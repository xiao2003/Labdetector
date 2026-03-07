from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List

from pc.app_identity import pc_bundle_root, pi_bundle_root
from pc.core.config import get_config, set_config

try:
    from pi.config import set_pi_config
except Exception:  # pragma: no cover - source/runtime import fallback
    set_pi_config = None


def _now_text() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _slugify(value: str) -> str:
    clean = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in str(value or "").strip())
    return clean[:72] or time.strftime("deployment_%Y%m%d_%H%M%S")


class ModelLinker:
    """Register and activate trained artifacts for runtime use."""

    def __init__(self) -> None:
        self.pc_root = Path(pc_bundle_root())
        self.pi_root = Path(pi_bundle_root())
        self.llm_root = self.pc_root / "models" / "llm_adapters"
        self.registry_root = self.pc_root / "models" / "registry"
        self.pi_detector_root = self.pi_root / "models" / "detectors"
        self.llm_root.mkdir(parents=True, exist_ok=True)
        self.registry_root.mkdir(parents=True, exist_ok=True)
        self.pi_detector_root.mkdir(parents=True, exist_ok=True)

    @property
    def llm_manifest_path(self) -> Path:
        return self.registry_root / "llm_deployments.json"

    @property
    def pi_manifest_path(self) -> Path:
        return self.registry_root / "pi_detector_deployments.json"

    def _load_manifest(self, path: Path) -> List[Dict[str, Any]]:
        if not path.exists():
            return []
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return []
        return [dict(item) for item in payload] if isinstance(payload, list) else []

    def _save_manifest(self, path: Path, rows: List[Dict[str, Any]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    def _upsert_manifest_row(self, path: Path, row: Dict[str, Any]) -> Dict[str, Any]:
        rows = [item for item in self._load_manifest(path) if item.get("deployment_id") != row.get("deployment_id")]
        rows.append(dict(row))
        rows.sort(key=lambda item: str(item.get("created_at", "")))
        self._save_manifest(path, rows)
        return row

    def list_llm_deployments(self) -> List[Dict[str, Any]]:
        return self._load_manifest(self.llm_manifest_path)

    def list_pi_detector_deployments(self) -> List[Dict[str, Any]]:
        return self._load_manifest(self.pi_manifest_path)

    def deployed_model_summary(self) -> Dict[str, Any]:
        llm_rows = self.list_llm_deployments()
        pi_rows = self.list_pi_detector_deployments()
        active_llm = str(get_config("local_llm.active_model", "") or "")
        active_pi = str(get_config("pi_detector.active_weights", "") or "")
        return {
            "llm_count": len(llm_rows),
            "pi_detector_count": len(pi_rows),
            "active_llm": active_llm,
            "active_pi_detector": active_pi,
            "llm": llm_rows[-10:],
            "pi_detectors": pi_rows[-10:],
        }

    def _copy_llm_runtime_files(self, source_dir: Path, target_dir: Path) -> List[str]:
        runtime_files: List[str] = []
        allowed_files = {
            "adapter_config.json",
            "adapter_model.bin",
            "adapter_model.safetensors",
            "tokenizer.json",
            "tokenizer.model",
            "tokenizer_config.json",
            "special_tokens_map.json",
            "generation_config.json",
            "config.json",
            "training_result.json",
        }
        target_dir.mkdir(parents=True, exist_ok=True)
        for item in source_dir.iterdir():
            if item.is_dir():
                continue
            if item.name not in allowed_files and not item.name.startswith("added_tokens"):
                continue
            shutil.copy2(item, target_dir / item.name)
            runtime_files.append(item.name)
        if not runtime_files:
            raise FileNotFoundError(f"LLM 微调目录缺少可部署文件: {source_dir}")
        return sorted(runtime_files)

    def resolve_llm_deployment(self, model_name: str = "") -> Dict[str, Any] | None:
        wanted = str(model_name or get_config("local_llm.active_model", "") or "").strip()
        rows = self.list_llm_deployments()
        if not rows:
            return None
        if not wanted:
            return dict(rows[-1])
        for row in reversed(rows):
            if wanted in {str(row.get("name", "")), str(row.get("deployment_id", "")), str(row.get("slug", ""))}:
                return dict(row)
        return None

    def resolve_pi_detector_deployment(self, target: str = "") -> Dict[str, Any] | None:
        wanted = str(target or get_config("pi_detector.active_weights", "") or "").strip()
        rows = self.list_pi_detector_deployments()
        if not rows:
            return None
        if not wanted:
            return dict(rows[-1])
        for row in reversed(rows):
            candidates = {
                str(row.get("name", "")),
                str(row.get("deployment_id", "")),
                str(row.get("slug", "")),
                str(row.get("weights_path", "")),
            }
            if wanted in candidates:
                return dict(row)
        return None

    def activate_llm_deployment(self, model_name: str = "") -> Dict[str, Any]:
        row = self.resolve_llm_deployment(model_name)
        if row is None:
            raise FileNotFoundError("未找到可激活的 LLM 部署模型。")
        set_config("local_llm.active_model", row["name"])
        set_config("local_llm.active_adapter_path", row["adapter_path"])
        set_config("local_llm.base_model", row["base_model"])
        set_config("training.llm_base_model", row["base_model"])
        row["active"] = True
        return row

    def activate_pi_detector_deployment(self, target: str = "") -> Dict[str, Any]:
        row = self.resolve_pi_detector_deployment(target)
        if row is None:
            raise FileNotFoundError("未找到可激活的 Pi 检测模型。")
        set_config("pi_detector.active_weights", row["weights_path"])
        set_config("training.pi_base_weights", row["weights_path"])
        if set_pi_config is not None:
            try:
                set_pi_config("detector.weights_path", row["weights_path"])
                set_pi_config("detector.conf", row.get("conf", 0.4))
            except Exception:
                pass
        row["active"] = True
        return row

    def register_llm_adapter(
        self,
        *,
        output_dir: str,
        base_model: str,
        workspace_dir: str = "",
        train_samples: int = 0,
        eval_samples: int = 0,
        activate: bool = True,
        deployment_name: str = "",
    ) -> Dict[str, Any]:
        source_dir = Path(str(output_dir)).expanduser().resolve()
        if not source_dir.exists():
            raise FileNotFoundError(f"LLM 微调输出目录不存在: {source_dir}")
        name = deployment_name.strip() or Path(workspace_dir or source_dir.name).name
        slug = _slugify(name)
        deployment_id = f"llm_{time.strftime('%Y%m%d_%H%M%S')}_{slug}"
        target_dir = self.llm_root / deployment_id
        runtime_files = self._copy_llm_runtime_files(source_dir, target_dir)
        row = {
            "deployment_id": deployment_id,
            "kind": "llm_adapter",
            "name": name,
            "slug": slug,
            "created_at": _now_text(),
            "workspace_dir": str(workspace_dir or ""),
            "source_dir": str(source_dir),
            "adapter_path": str(target_dir),
            "base_model": str(base_model),
            "train_samples": int(train_samples or 0),
            "eval_samples": int(eval_samples or 0),
            "runtime_files": runtime_files,
            "active": False,
        }
        (target_dir / "deployment.json").write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8")
        self._upsert_manifest_row(self.llm_manifest_path, row)
        if activate:
            row = self.activate_llm_deployment(row["deployment_id"])
        return row

    def register_pi_detector(
        self,
        *,
        weights_path: str,
        workspace_dir: str = "",
        sample_count: int = 0,
        class_names: List[str] | None = None,
        conf: float = 0.4,
        activate: bool = True,
        deployment_name: str = "",
    ) -> Dict[str, Any]:
        source_file = Path(str(weights_path)).expanduser().resolve()
        if not source_file.exists():
            raise FileNotFoundError(f"Pi 检测模型权重不存在: {source_file}")
        name = deployment_name.strip() or Path(workspace_dir or source_file.stem).name
        slug = _slugify(name)
        deployment_id = f"pi_{time.strftime('%Y%m%d_%H%M%S')}_{slug}"
        target_file = self.pi_detector_root / f"{deployment_id}{source_file.suffix.lower() or '.pt'}"
        shutil.copy2(source_file, target_file)
        row = {
            "deployment_id": deployment_id,
            "kind": "pi_detector",
            "name": name,
            "slug": slug,
            "created_at": _now_text(),
            "workspace_dir": str(workspace_dir or ""),
            "source_file": str(source_file),
            "weights_path": str(target_file),
            "sample_count": int(sample_count or 0),
            "class_names": list(class_names or []),
            "conf": float(conf),
            "active": False,
        }
        metadata_path = target_file.with_suffix(".json")
        metadata_path.write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8")
        self._upsert_manifest_row(self.pi_manifest_path, row)
        if activate:
            row = self.activate_pi_detector_deployment(row["deployment_id"])
        return row


model_linker = ModelLinker()
