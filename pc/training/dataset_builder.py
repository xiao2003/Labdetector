from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List

from pc.app_identity import resource_path
from pc.core.experiment_archive import get_experiment_archive


class DatasetBuilder:
    def __init__(self) -> None:
        self.training_root = Path(resource_path("pc/training_runs"))
        self.training_root.mkdir(parents=True, exist_ok=True)
        self.voice_root = Path(resource_path("pc/log/voice_rounds"))

    def _list_voice_round_rows(self) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        if not self.voice_root.exists():
            return rows
        for session_dir in sorted(self.voice_root.iterdir()):
            if not session_dir.is_dir():
                continue
            for item in sorted(session_dir.glob("round_*.json")):
                try:
                    payload = json.loads(item.read_text(encoding="utf-8"))
                except Exception:
                    continue
                payload["round_path"] = str(item)
                rows.append(payload)
        return rows

    def _list_archive_rows(self) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        archive = get_experiment_archive()
        for session in archive.list_sessions(limit=200):
            session_id = str(session.get("session_id", ""))
            if not session_id:
                continue
            try:
                detail = archive.get_session_detail(session_id)
            except Exception:
                continue
            for event in detail.get("events", []):
                rows.append(event)
        return rows

    def pseudo_label_archive_frames(self) -> List[Dict[str, Any]]:
        labels: List[Dict[str, Any]] = []
        for event in self._list_archive_rows():
            payload = dict(event.get("payload") or {})
            frame_path = str(payload.get("frame_path") or payload.get("image_path") or "").strip()
            if not frame_path:
                continue
            path = Path(frame_path)
            if not path.exists() or not path.is_file():
                continue
            label = str(payload.get("event_name") or payload.get("event_type") or event.get("title") or "observation")
            labels.append(
                {
                    "image_path": str(path),
                    "label": label,
                    "session_id": event.get("session_id", ""),
                    "event_type": event.get("event_type", ""),
                    "timestamp": event.get("timestamp", ""),
                }
            )
        return labels

    def prepare_yolo_dataset(self, workspace_dir: Path) -> Dict[str, Any]:
        dataset_dir = workspace_dir / "pi_detector"
        image_dir = dataset_dir / "images" / "train"
        label_dir = dataset_dir / "labels" / "train"
        image_dir.mkdir(parents=True, exist_ok=True)
        label_dir.mkdir(parents=True, exist_ok=True)

        pseudo_rows = self.pseudo_label_archive_frames()
        names: Dict[str, int] = {}
        copied = 0
        for index, row in enumerate(pseudo_rows, start=1):
            source = Path(row["image_path"])
            class_name = str(row["label"] or "observation").replace(" ", "_")
            if class_name not in names:
                names[class_name] = len(names)
            target = image_dir / f"sample_{index:05d}{source.suffix.lower()}"
            try:
                shutil.copy2(source, target)
            except Exception:
                continue
            label_file = label_dir / f"sample_{index:05d}.txt"
            label_file.write_text(f"{names[class_name]} 0.5 0.5 1.0 1.0\n", encoding="utf-8")
            copied += 1

        yaml_lines = [
            f"path: {dataset_dir.as_posix()}",
            "train: images/train",
            "val: images/train",
            f"nc: {max(len(names), 1)}",
            "names:",
        ]
        if names:
            for label, idx in sorted(names.items(), key=lambda item: item[1]):
                yaml_lines.append(f"  {idx}: {label}")
        else:
            yaml_lines.append("  0: observation")
        (dataset_dir / "dataset.yaml").write_text("\n".join(yaml_lines) + "\n", encoding="utf-8")
        return {
            "dataset_dir": str(dataset_dir),
            "sample_count": copied,
            "class_names": [label for label, _ in sorted(names.items(), key=lambda item: item[1])] or ["observation"],
        }

    def build_training_workspace(self, workspace_name: str = "") -> Dict[str, Any]:
        stamp = time.strftime("%Y%m%d_%H%M%S")
        name = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in (workspace_name or "training_workspace"))
        workspace_dir = self.training_root / f"{stamp}_{name[:48] or 'training_workspace'}"
        workspace_dir.mkdir(parents=True, exist_ok=True)

        llm_dir = workspace_dir / "llm_sft"
        llm_dir.mkdir(parents=True, exist_ok=True)
        train_rows: List[Dict[str, Any]] = []
        for row in self._list_voice_round_rows():
            prompt = str(row.get("prompt") or "").strip()
            response = str(row.get("response") or "").strip()
            if not prompt or not response:
                continue
            meta = {
                "session_id": row.get("session_id", ""),
                "project_name": row.get("project_name", ""),
                "experiment_name": row.get("experiment_name", ""),
                "operator_name": row.get("operator_name", ""),
                "tags": row.get("tags", []),
                "source": row.get("source", ""),
            }
            train_rows.append({"instruction": prompt, "output": response, "metadata": meta})

        eval_rows = train_rows[-max(1, min(len(train_rows) // 5, 20)):] if train_rows else []
        (llm_dir / "train.jsonl").write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in train_rows), encoding="utf-8")
        (llm_dir / "eval.jsonl").write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in eval_rows), encoding="utf-8")

        detector_summary = self.prepare_yolo_dataset(workspace_dir)
        summary = {
            "workspace_dir": str(workspace_dir),
            "llm_train_samples": len(train_rows),
            "llm_eval_samples": len(eval_rows),
            "detector_train_samples": detector_summary["sample_count"],
            "detector_class_names": detector_summary["class_names"],
            "llm_train_path": str(llm_dir / "train.jsonl"),
            "llm_eval_path": str(llm_dir / "eval.jsonl"),
            "detector_dataset_path": detector_summary["dataset_dir"],
        }
        (workspace_dir / "workspace_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        return summary


dataset_builder = DatasetBuilder()
