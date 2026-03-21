from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List

from pc.training.dataset_importer import IMAGE_EXTENSIONS


def _slugify(value: str) -> str:
    clean = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in value.strip())
    return clean[:64] or "label"


class VisionAnnotationStore:
    def _dataset_root(self, workspace_dir: str | Path) -> Path:
        root = Path(workspace_dir).expanduser().resolve() / "pi_detector"
        (root / "images" / "train").mkdir(parents=True, exist_ok=True)
        (root / "labels" / "train").mkdir(parents=True, exist_ok=True)
        return root

    def _meta_path(self, workspace_dir: str | Path) -> Path:
        return self._dataset_root(workspace_dir) / "annotation_meta.json"

    def _dataset_yaml_path(self, workspace_dir: str | Path) -> Path:
        return self._dataset_root(workspace_dir) / "dataset.yaml"

    def _workspace_summary_path(self, workspace_dir: str | Path) -> Path:
        return Path(workspace_dir).expanduser().resolve() / "workspace_summary.json"

    def _load_meta(self, workspace_dir: str | Path) -> Dict[str, Any]:
        path = self._meta_path(workspace_dir)
        if not path.exists():
            return {"class_names": [], "images": {}}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {"class_names": [], "images": {}}
        payload.setdefault("class_names", [])
        payload.setdefault("images", {})
        return payload

    def _save_meta(self, workspace_dir: str | Path, payload: Dict[str, Any]) -> None:
        self._meta_path(workspace_dir).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _write_dataset_yaml(self, workspace_dir: str | Path, class_names: List[str]) -> None:
        dataset_root = self._dataset_root(workspace_dir)
        labels = class_names or ["observation"]
        lines = [
            f"path: {dataset_root.as_posix()}",
            "train: images/train",
            "val: images/train",
            f"nc: {len(labels)}",
            "names:",
        ]
        for index, label in enumerate(labels):
            lines.append(f"  {index}: {label}")
        self._dataset_yaml_path(workspace_dir).write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _update_workspace_summary(self, workspace_dir: str | Path, class_names: List[str]) -> None:
        summary_path = self._workspace_summary_path(workspace_dir)
        payload: Dict[str, Any] = {}
        if summary_path.exists():
            try:
                payload = json.loads(summary_path.read_text(encoding="utf-8"))
            except Exception:
                payload = {}
        image_dir = self._dataset_root(workspace_dir) / "images" / "train"
        sample_count = len([item for item in image_dir.iterdir() if item.is_file()]) if image_dir.exists() else 0
        payload["detector_train_samples"] = sample_count
        payload["detector_class_names"] = class_names or ["observation"]
        payload["detector_dataset_path"] = str(self._dataset_root(workspace_dir))
        summary_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def import_images(self, workspace_dir: str | Path, paths: Iterable[str]) -> Dict[str, Any]:
        dataset_root = self._dataset_root(workspace_dir)
        image_dir = dataset_root / "images" / "train"
        label_dir = dataset_root / "labels" / "train"
        meta = self._load_meta(workspace_dir)
        imported: List[str] = []

        for raw in paths:
            path = Path(str(raw)).expanduser()
            if not path.exists():
                continue
            source_files = [path] if path.is_file() else [item for item in path.rglob("*") if item.is_file()]
            for source in source_files:
                if source.suffix.lower() not in IMAGE_EXTENSIONS:
                    continue
                target = image_dir / source.name
                if target.exists():
                    target = image_dir / f"{source.stem}_{int(time.time() * 1000)}{source.suffix.lower()}"
                shutil.copy2(source, target)
                label_path = label_dir / f"{target.stem}.txt"
                if not label_path.exists():
                    label_path.write_text("", encoding="utf-8")
                meta["images"][target.name] = {
                    "image_path": str(target),
                    "label_path": str(label_path),
                    "boxes": [],
                    "size": [],
                }
                imported.append(target.name)

        self._save_meta(workspace_dir, meta)
        self._write_dataset_yaml(workspace_dir, list(meta.get("class_names", [])))
        self._update_workspace_summary(workspace_dir, list(meta.get("class_names", [])))
        return {
            "imported_count": len(imported),
            "images": imported,
            "dataset_dir": str(dataset_root),
        }

    def list_images(self, workspace_dir: str | Path) -> List[Dict[str, Any]]:
        dataset_root = self._dataset_root(workspace_dir)
        image_dir = dataset_root / "images" / "train"
        meta = self._load_meta(workspace_dir)
        rows: List[Dict[str, Any]] = []
        for image_path in sorted(image_dir.glob("*")):
            if not image_path.is_file():
                continue
            row = dict(meta.get("images", {}).get(image_path.name) or {})
            row["name"] = image_path.name
            row["image_path"] = str(image_path)
            row.setdefault("label_path", str(dataset_root / "labels" / "train" / f"{image_path.stem}.txt"))
            row.setdefault("boxes", [])
            rows.append(row)
        return rows

    def get_classes(self, workspace_dir: str | Path) -> List[str]:
        return list(self._load_meta(workspace_dir).get("class_names", []))

    def save_annotations(
        self,
        workspace_dir: str | Path,
        image_name: str,
        image_width: int,
        image_height: int,
        boxes: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        if not image_name:
            raise ValueError("请先选择图片。")
        if image_width <= 0 or image_height <= 0:
            raise ValueError("图片尺寸无效，无法保存标注。")

        meta = self._load_meta(workspace_dir)
        class_names = list(meta.get("class_names", []))
        label_dir = self._dataset_root(workspace_dir) / "labels" / "train"
        label_path = label_dir / f"{Path(image_name).stem}.txt"
        serialized_boxes: List[Dict[str, Any]] = []
        lines: List[str] = []

        for item in boxes:
            class_name = _slugify(str(item.get("class_name") or "observation"))
            if class_name not in class_names:
                class_names.append(class_name)
            class_id = class_names.index(class_name)
            x1 = max(0.0, min(float(item.get("x1", 0.0)), float(image_width)))
            y1 = max(0.0, min(float(item.get("y1", 0.0)), float(image_height)))
            x2 = max(0.0, min(float(item.get("x2", 0.0)), float(image_width)))
            y2 = max(0.0, min(float(item.get("y2", 0.0)), float(image_height)))
            left = min(x1, x2)
            right = max(x1, x2)
            top = min(y1, y2)
            bottom = max(y1, y2)
            width = max(0.0, right - left)
            height = max(0.0, bottom - top)
            if width < 2 or height < 2:
                continue
            center_x = (left + right) / 2.0 / float(image_width)
            center_y = (top + bottom) / 2.0 / float(image_height)
            norm_w = width / float(image_width)
            norm_h = height / float(image_height)
            lines.append(f"{class_id} {center_x:.6f} {center_y:.6f} {norm_w:.6f} {norm_h:.6f}")
            serialized_boxes.append(
                {
                    "class_name": class_name,
                    "class_id": class_id,
                    "x1": round(left, 2),
                    "y1": round(top, 2),
                    "x2": round(right, 2),
                    "y2": round(bottom, 2),
                }
            )

        label_path.write_text(("\n".join(lines) + "\n") if lines else "", encoding="utf-8")
        meta.setdefault("images", {})
        meta["images"][image_name] = {
            "image_path": str(self._dataset_root(workspace_dir) / "images" / "train" / image_name),
            "label_path": str(label_path),
            "boxes": serialized_boxes,
            "size": [int(image_width), int(image_height)],
        }
        meta["class_names"] = class_names
        self._save_meta(workspace_dir, meta)
        self._write_dataset_yaml(workspace_dir, class_names)
        self._update_workspace_summary(workspace_dir, class_names)
        return {
            "image_name": image_name,
            "box_count": len(serialized_boxes),
            "class_names": class_names,
            "label_path": str(label_path),
        }


annotation_store = VisionAnnotationStore()
