#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import json
import shutil
import time
import zipfile
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
DIST_ROOT = ROOT / "dist" / "NeuroLab Hub SilentDir"
DEFAULT_RELEASE_ROOT = ROOT.parent / "release"

ROOT_INCLUDE_DIRS = {
    "assets",
    "docs",
    "pc",
    "pi",
}

ROOT_INCLUDE_FILES = {
    "README.md",
    "README_QUICKSTART.txt",
    "VERSION",
    "config.ini",
    "launcher.py",
    "project_identity.json",
}

PC_MUTABLE_DIRS = {
    Path("log"),
    Path("training_assets"),
    Path("training_runs"),
    Path("knowledge_base") / "docs",
    Path("knowledge_base") / "faiss_index",
    Path("knowledge_base") / "scopes",
    Path("models") / "experts",
    Path("models") / "llm_adapters",
    Path("models") / "registry",
}

PC_MUTABLE_FILES = {
    Path("knowledge_base") / "structured_kb.sqlite3",
}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="构建干净的 NeuroLab Hub 发布包")
    parser.add_argument(
        "--release-root",
        default=str(DEFAULT_RELEASE_ROOT),
        help="发布输出根目录",
    )
    parser.add_argument(
        "--version",
        default=(ROOT / "VERSION").read_text(encoding="utf-8").strip(),
        help="发布版本号",
    )
    parser.add_argument(
        "--label",
        default=time.strftime("%Y%m%d_%H%M%S"),
        help="本次构建标签，用于区分不同发布目录",
    )
    return parser.parse_args()


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _copy_file(src: Path, dst: Path) -> None:
    _ensure_dir(dst.parent)
    shutil.copy2(src, dst)


def _should_skip_root_entry(entry: Path) -> bool:
    if entry.name == "__pycache__":
        return True
    if entry.is_dir():
        return entry.name not in ROOT_INCLUDE_DIRS
    return entry.name not in ROOT_INCLUDE_FILES


def _should_skip_pc_entry(relative_path: Path) -> bool:
    if "__pycache__" in relative_path.parts:
        return True
    if relative_path in PC_MUTABLE_DIRS:
        return True
    if relative_path in PC_MUTABLE_FILES:
        return True
    for blocked in PC_MUTABLE_DIRS:
        if blocked in relative_path.parents:
            return True
    return False


def _iter_source_files() -> Iterable[tuple[Path, Path]]:
    for entry in ROOT.iterdir():
        if _should_skip_root_entry(entry):
            continue
        if entry.is_file():
            yield entry, Path("APP") / entry.name
            continue
        if entry.name != "pc":
            for child in entry.rglob("*"):
                if child.is_dir() or "__pycache__" in child.parts:
                    continue
                yield child, Path("APP") / child.relative_to(ROOT)
            continue
        for child in entry.rglob("*"):
            if child.is_dir():
                continue
            relative_to_pc = child.relative_to(entry)
            if _should_skip_pc_entry(relative_to_pc):
                continue
            yield child, Path("APP") / child.relative_to(ROOT)


def _copy_runtime_dirs(stage_dir: Path) -> None:
    exe_target = stage_dir / "NeuroLab Hub SilentDir.exe"
    internal_target = stage_dir / "_internal"
    _copy_file(DIST_ROOT / "NeuroLab Hub SilentDir.exe", exe_target)
    shutil.copytree(DIST_ROOT / "_internal", internal_target, dirs_exist_ok=True)


def _copy_app_tree(stage_dir: Path) -> dict[str, int]:
    copied_files = 0
    copied_bytes = 0
    for src, relative_dst in _iter_source_files():
        dst = stage_dir / relative_dst
        _copy_file(src, dst)
        copied_files += 1
        copied_bytes += src.stat().st_size
    return {"copied_files": copied_files, "copied_bytes": copied_bytes}


def _ensure_clean_runtime_placeholders(stage_dir: Path) -> None:
    app_pc = stage_dir / "APP" / "pc"
    for directory in (
        app_pc / "log",
        app_pc / "training_assets",
        app_pc / "training_runs",
        app_pc / "knowledge_base" / "docs",
        app_pc / "knowledge_base" / "faiss_index",
        app_pc / "knowledge_base" / "scopes",
        app_pc / "models" / "experts",
        app_pc / "models" / "llm_adapters",
        app_pc / "models" / "registry",
    ):
        _ensure_dir(directory)


def _write_manifest(stage_dir: Path, manifest: dict[str, object]) -> Path:
    manifest_path = stage_dir / "release_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest_path


def _zip_stage(stage_dir: Path, zip_path: Path) -> None:
    _ensure_dir(zip_path.parent)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for item in stage_dir.rglob("*"):
            if item.is_dir():
                continue
            archive.write(item, item.relative_to(stage_dir.parent))


def build_release_package(release_root: Path, version: str, label: str) -> dict[str, object]:
    if not DIST_ROOT.exists():
        raise FileNotFoundError(f"未找到打包输出目录: {DIST_ROOT}")
    if not (DIST_ROOT / "NeuroLab Hub SilentDir.exe").exists():
        raise FileNotFoundError("未找到 SilentDir 可执行文件。")
    if not (DIST_ROOT / "_internal").exists():
        raise FileNotFoundError("未找到 SilentDir 运行时目录 _internal。")

    stage_parent = release_root / f"stage_{label}"
    stage_dir = stage_parent / "NeuroLab Hub SilentDir"
    zip_path = release_root / f"NeuroLab_Hub_{version}_{label}.zip"
    _ensure_dir(stage_dir)

    _copy_runtime_dirs(stage_dir)
    copy_stats = _copy_app_tree(stage_dir)
    _ensure_clean_runtime_placeholders(stage_dir)

    manifest = {
        "version": version,
        "label": label,
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "project_root": str(ROOT),
        "dist_root": str(DIST_ROOT),
        "stage_dir": str(stage_dir),
        "zip_path": str(zip_path),
        "copy_stats": copy_stats,
        "excluded_pc_dirs": [str(path).replace("\\", "/") for path in sorted(PC_MUTABLE_DIRS)],
        "excluded_pc_files": [str(path).replace("\\", "/") for path in sorted(PC_MUTABLE_FILES)],
    }
    manifest_path = _write_manifest(stage_dir, manifest)
    manifest["manifest_path"] = str(manifest_path)

    _zip_stage(stage_dir, zip_path)
    manifest["zip_size"] = zip_path.stat().st_size
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def main() -> int:
    args = _parse_args()
    manifest = build_release_package(
        release_root=Path(args.release_root).resolve(),
        version=str(args.version).strip(),
        label=str(args.label).strip(),
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
