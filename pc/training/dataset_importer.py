from __future__ import annotations

import csv
import json
import shutil
import time
import zipfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from pc.app_identity import resource_path


LLM_EXTENSIONS = {".jsonl", ".json", ".csv", ".txt", ".md"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def _timestamp() -> str:
    return time.strftime("%Y%m%d_%H%M%S")


def _slugify(value: str) -> str:
    clean = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in value.strip())
    return clean[:64] or "dataset"


class DatasetImporter:
    def __init__(self) -> None:
        self.root = Path(resource_path("pc/training_assets"))
        self.llm_root = self.root / "llm"
        self.pi_root = self.root / "pi_detector"
        self.llm_root.mkdir(parents=True, exist_ok=True)
        self.pi_root.mkdir(parents=True, exist_ok=True)

    @property
    def llm_records_path(self) -> Path:
        return self.llm_root / "records.jsonl"

    def _iter_files(self, inputs: Iterable[str], allowed_exts: set[str] | None = None) -> List[Path]:
        files: List[Path] = []
        for raw in inputs:
            path = Path(str(raw)).expanduser()
            if not path.exists():
                continue
            if path.is_file():
                if allowed_exts is None or path.suffix.lower() in allowed_exts:
                    files.append(path.resolve())
                continue
            for item in path.rglob("*"):
                if item.is_file() and (allowed_exts is None or item.suffix.lower() in allowed_exts):
                    files.append(item.resolve())
        unique: List[Path] = []
        seen = set()
        for item in files:
            key = str(item)
            if key in seen:
                continue
            seen.add(key)
            unique.append(item)
        return unique

    def _copy_unique(self, source: Path, target_dir: Path) -> Path:
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / source.name
        if target.exists():
            target = target_dir / f"{source.stem}_{int(time.time())}{source.suffix}"
        shutil.copy2(source, target)
        return target

    def _normalize_llm_row(self, row: Dict[str, Any]) -> Dict[str, Any] | None:
        instruction = ""
        output = ""
        for key in ("instruction", "prompt", "question", "input", "query"):
            value = str(row.get(key) or "").strip()
            if value:
                instruction = value
                break
        for key in ("output", "response", "answer", "target", "completion"):
            value = str(row.get(key) or "").strip()
            if value:
                output = value
                break
        if not instruction or not output:
            return None
        metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        return {
            "instruction": instruction,
            "output": output,
            "metadata": metadata or {},
        }

    def _load_llm_rows_from_file(self, path: Path) -> List[Dict[str, Any]]:
        suffix = path.suffix.lower()
        rows: List[Dict[str, Any]] = []
        if suffix == ".jsonl":
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                payload = json.loads(line)
                if isinstance(payload, dict):
                    rows.append(payload)
        elif suffix == ".json":
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, list):
                rows.extend(item for item in payload if isinstance(item, dict))
            elif isinstance(payload, dict):
                rows.append(payload)
        elif suffix == ".csv":
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                rows.extend(dict(item) for item in reader)
        elif suffix in {".txt", ".md"}:
            text = path.read_text(encoding="utf-8")
            blocks = [block.strip() for block in text.split("\n\n") if block.strip()]
            for block in blocks:
                prompt = ""
                answer = ""
                for line in block.splitlines():
                    clean = line.strip()
                    if clean.startswith(("Q:", "问:", "问题:", "Prompt:")):
                        prompt = clean.split(":", 1)[1].strip()
                    elif clean.startswith(("A:", "答:", "回答:", "Answer:")):
                        answer = clean.split(":", 1)[1].strip()
                if prompt and answer:
                    rows.append({"instruction": prompt, "output": answer})
        return rows

    def list_llm_records(self) -> List[Dict[str, Any]]:
        if not self.llm_records_path.exists():
            return []
        rows: List[Dict[str, Any]] = []
        for line in self.llm_records_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except Exception:
                continue
            if isinstance(payload, dict):
                rows.append(payload)
        return rows

    def import_llm_dataset(self, paths: List[str]) -> Dict[str, Any]:
        if not paths:
            raise ValueError("请至少提供一个 LLM 训练数据文件或目录。")
        files = self._iter_files(paths, LLM_EXTENSIONS)
        if not files:
            raise FileNotFoundError("未找到可导入的 LLM 训练数据文件。")

        batch_dir = self.llm_root / "imports" / f"{_timestamp()}_{_slugify(files[0].stem)}"
        raw_dir = batch_dir / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)

        imported_files = 0
        new_rows: List[Dict[str, Any]] = []
        for source in files:
            target = self._copy_unique(source, raw_dir)
            imported_files += 1
            for row in self._load_llm_rows_from_file(target):
                normalized = self._normalize_llm_row(row)
                if normalized is not None:
                    normalized.setdefault("metadata", {})["source_file"] = source.name
                    new_rows.append(normalized)

        merged = self.list_llm_records() + new_rows
        deduped: List[Dict[str, Any]] = []
        seen: set[Tuple[str, str]] = set()
        for row in merged:
            key = (str(row.get("instruction") or "").strip(), str(row.get("output") or "").strip())
            if not key[0] or not key[1] or key in seen:
                continue
            seen.add(key)
            deduped.append(row)

        self.llm_records_path.parent.mkdir(parents=True, exist_ok=True)
        self.llm_records_path.write_text(
            "\n".join(json.dumps(row, ensure_ascii=False) for row in deduped),
            encoding="utf-8",
        )
        summary = {
            "imported_count": imported_files,
            "sample_count": len(new_rows),
            "total_sample_count": len(deduped),
            "target_path": str(batch_dir),
            "normalized_path": str(self.llm_records_path),
        }
        (batch_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        return summary

    def _load_yaml_names(self, path: Path) -> List[str]:
        try:
            import yaml  # type: ignore

            payload = yaml.safe_load(path.read_text(encoding="utf-8"))
            names = payload.get("names") if isinstance(payload, dict) else None
            if isinstance(names, list):
                return [str(item) for item in names]
            if isinstance(names, dict):
                return [str(names[key]) for key in sorted(names)]
        except Exception:
            pass
        names: List[str] = []
        in_names = False
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("names:"):
                in_names = True
                continue
            if in_names:
                stripped = line.strip()
                if not stripped or ":" not in stripped:
                    continue
                _, value = stripped.split(":", 1)
                names.append(value.strip().strip('"').strip("'"))
        return names

    def _write_dataset_yaml(self, path: Path, class_names: List[str]) -> None:
        lines = [
            f"path: {path.parent.as_posix()}",
            "train: images/train",
            "val: images/train",
            f"nc: {max(1, len(class_names))}",
            "names:",
        ]
        labels = class_names or ["observation"]
        for index, label in enumerate(labels):
            lines.append(f"  {index}: {label}")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _extract_zip(self, source: Path, target_dir: Path) -> Path:
        target_dir.mkdir(parents=True, exist_ok=True)
        extract_root = target_dir / source.stem
        if extract_root.exists():
            extract_root = target_dir / f"{source.stem}_{int(time.time())}"
        extract_root.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(source, "r") as archive:
            archive.extractall(extract_root)
        return extract_root

    def _copy_pi_dataset_dir(self, source_root: Path, batch_root: Path) -> Dict[str, Any]:
        dataset_dir = batch_root / _slugify(source_root.name)
        if dataset_dir.exists():
            dataset_dir = batch_root / f"{_slugify(source_root.name)}_{int(time.time())}"
        shutil.copytree(source_root, dataset_dir)
        yaml_path = None
        for candidate in (dataset_dir / "dataset.yaml", dataset_dir / "data.yaml"):
            if candidate.exists():
                yaml_path = candidate
                break
        class_names = self._load_yaml_names(yaml_path) if yaml_path else []
        if yaml_path is None:
            yaml_path = dataset_dir / "dataset.yaml"
            self._write_dataset_yaml(yaml_path, class_names)
        image_dir = dataset_dir / "images" / "train"
        sample_count = len([item for item in image_dir.glob("*") if item.is_file()]) if image_dir.exists() else 0
        return {
            "dataset_dir": str(dataset_dir),
            "dataset_yaml": str(yaml_path),
            "sample_count": sample_count,
            "class_names": class_names or ["observation"],
        }

    def _build_pi_dataset_from_files(self, source_files: List[Path], batch_root: Path, batch_name: str) -> Dict[str, Any]:
        dataset_dir = batch_root / _slugify(batch_name)
        image_dir = dataset_dir / "images" / "train"
        label_dir = dataset_dir / "labels" / "train"
        image_dir.mkdir(parents=True, exist_ok=True)
        label_dir.mkdir(parents=True, exist_ok=True)

        sample_count = 0
        max_class_id = -1
        for index, image_path in enumerate(source_files, start=1):
            if image_path.suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            label_path = image_path.with_suffix(".txt")
            if not label_path.exists():
                continue
            image_target = image_dir / f"sample_{index:05d}{image_path.suffix.lower()}"
            label_target = label_dir / f"sample_{index:05d}.txt"
            shutil.copy2(image_path, image_target)
            shutil.copy2(label_path, label_target)
            for line in label_target.read_text(encoding="utf-8").splitlines():
                parts = line.strip().split()
                if parts and parts[0].isdigit():
                    max_class_id = max(max_class_id, int(parts[0]))
            sample_count += 1

        class_names = [f"class_{index}" for index in range(max_class_id + 1)] or ["observation"]
        yaml_path = dataset_dir / "dataset.yaml"
        self._write_dataset_yaml(yaml_path, class_names)
        return {
            "dataset_dir": str(dataset_dir),
            "dataset_yaml": str(yaml_path),
            "sample_count": sample_count,
            "class_names": class_names,
        }

    def import_pi_dataset(self, paths: List[str]) -> Dict[str, Any]:
        if not paths:
            raise ValueError("请至少提供一个 Pi 训练数据目录、压缩包或标注图片目录。")
        batch_root = self.pi_root / "datasets" / f"{_timestamp()}_{_slugify(Path(paths[0]).stem or 'pi_dataset')}"
        batch_root.mkdir(parents=True, exist_ok=True)

        imported_count = 0
        sample_count = 0
        dataset_yaml = ""
        class_names: List[str] = []
        direct_image_files: List[Path] = []

        for raw in paths:
            source = Path(str(raw)).expanduser()
            if not source.exists():
                continue
            if source.is_file() and source.suffix.lower() == ".zip":
                extracted = self._extract_zip(source, batch_root / "unzipped")
                summary = self._copy_pi_dataset_dir(extracted, batch_root)
                imported_count += 1
                sample_count += int(summary["sample_count"])
                dataset_yaml = summary["dataset_yaml"]
                class_names = list(summary["class_names"])
                continue
            if source.is_dir():
                if (source / "dataset.yaml").exists() or (source / "data.yaml").exists():
                    summary = self._copy_pi_dataset_dir(source, batch_root)
                    imported_count += 1
                    sample_count += int(summary["sample_count"])
                    dataset_yaml = summary["dataset_yaml"]
                    class_names = list(summary["class_names"])
                else:
                    direct_image_files.extend(self._iter_files([str(source)], IMAGE_EXTENSIONS))
                continue
            if source.is_file() and source.suffix.lower() in IMAGE_EXTENSIONS:
                direct_image_files.append(source.resolve())

        if direct_image_files:
            summary = self._build_pi_dataset_from_files(direct_image_files, batch_root, "manual_import")
            imported_count += len(direct_image_files)
            sample_count += int(summary["sample_count"])
            dataset_yaml = summary["dataset_yaml"]
            class_names = list(summary["class_names"])

        if not dataset_yaml:
            raise FileNotFoundError("未找到可用于 Pi 训练的标注数据。")

        result = {
            "imported_count": imported_count,
            "sample_count": sample_count,
            "dataset_yaml": dataset_yaml,
            "class_names": class_names or ["observation"],
            "target_path": str(batch_root),
        }
        (batch_root / "summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return result

    def list_pi_assets(self) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        datasets_root = self.pi_root / "datasets"
        if not datasets_root.exists():
            return rows
        for batch_dir in sorted(datasets_root.iterdir()):
            if not batch_dir.is_dir():
                continue
            for yaml_path in batch_dir.rglob("dataset.yaml"):
                dataset_dir = yaml_path.parent
                image_dir = dataset_dir / "images" / "train"
                class_names = self._load_yaml_names(yaml_path) or ["observation"]
                rows.append(
                    {
                        "dataset_dir": str(dataset_dir),
                        "dataset_yaml": str(yaml_path),
                        "sample_count": len([item for item in image_dir.glob("*") if item.is_file()]) if image_dir.exists() else 0,
                        "class_names": class_names,
                    }
                )
        return rows

    def asset_summary(self) -> Dict[str, Any]:
        llm_rows = self.list_llm_records()
        pi_assets = self.list_pi_assets()
        return {
            "llm_total_samples": len(llm_rows),
            "pi_dataset_count": len(pi_assets),
            "pi_total_samples": sum(int(item.get("sample_count", 0)) for item in pi_assets),
            "llm_records_path": str(self.llm_records_path),
            "pi_datasets": pi_assets,
        }


dataset_importer = DatasetImporter()
