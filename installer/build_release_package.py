#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import json
import subprocess
import shutil
import time
import zipfile
from pathlib import Path
from typing import Any, Dict, Iterable

from pc.core.orchestrator_runtime import materialize_model_bundle, materialize_runtime_bundle
from pc.core.runtime_assets import vosk_model_dir


ROOT = Path(__file__).resolve().parents[1]
DIST_ROOT = ROOT / "dist" / "NeuroLab Hub SilentDir"
DEFAULT_RELEASE_ROOT = ROOT.parent / "release"
INSTALLER_SCRIPT = ROOT / "installer" / "NeuroLab_Hub.iss"
ISCC_CANDIDATES = (
    Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"),
    Path(r"C:\Program Files\Inno Setup 6\ISCC.exe"),
)

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
    internal_target = stage_dir / "_internal"
    source_exe = DIST_ROOT / "NeuroLab Hub SilentDir.exe"
    for launcher_name in (
        "NeuroLab Hub SilentDir.exe",
        "NeuroLab Hub.exe",
        "NeuroLab Hub LLM.exe",
        "NeuroLab Hub Vision.exe",
    ):
        _copy_file(source_exe, stage_dir / launcher_name)
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


def _copy_bundled_vosk_assets(stage_dir: Path) -> dict[str, object]:
    source_dir = vosk_model_dir()
    target_dir = stage_dir / "APP" / "runtime_data" / "speech_assets" / source_dir.name
    if not source_dir.exists() or not (source_dir / "am" / "final.mdl").exists():
        raise FileNotFoundError(f"Vosk 离线语音模型缺失，无法内置到交付物: {source_dir}")
    if target_dir.exists():
        shutil.rmtree(target_dir)
    copied_files = 0
    copied_bytes = 0
    for item in source_dir.rglob("*"):
        if item.is_dir():
            continue
        if item.name.endswith('.zip'):
            continue
        relative = item.relative_to(source_dir)
        destination = target_dir / relative
        _copy_file(item, destination)
        copied_files += 1
        copied_bytes += item.stat().st_size
    return {
        "source_dir": str(source_dir),
        "target_dir": str(target_dir),
        "copied_files": copied_files,
        "copied_bytes": copied_bytes,
    }


def _materialize_orchestrator_runtime(stage_dir: Path) -> Dict[str, Any]:
    runtime_target = stage_dir / "APP" / "pc" / "runtime" / "llm_orchestrator"
    materialized = materialize_runtime_bundle(runtime_target)
    manifest_path = stage_dir / "APP" / "pc" / "models" / "orchestrator" / "orchestrator_assets.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"固定管家层资产清单缺失: {manifest_path}")
    if not (runtime_target / "llama-cli.exe").exists():
        raise FileNotFoundError(f"固定管家层 runtime 缺少 llama-cli.exe: {runtime_target}")
    return {
        "runtime_dir": str(runtime_target),
        "manifest_path": str(manifest_path),
        "copied_files": list(materialized.get("copied_files") or []),
    }


def _materialize_orchestrator_model(stage_dir: Path) -> Dict[str, Any]:
    manifest_path = stage_dir / "APP" / "pc" / "models" / "orchestrator" / "orchestrator_assets.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"固定管家层资产清单缺失: {manifest_path}")
    staged_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    model_meta = dict(staged_manifest.get("model") or {})
    filename = str(model_meta.get("filename") or "").strip()
    if not filename:
        raise FileNotFoundError("固定管家层模型清单缺少 filename。")
    model_target = stage_dir / "APP" / "pc" / "models" / "orchestrator" / filename
    materialized = materialize_model_bundle(model_target)
    model_meta["size"] = int(materialized.get("size") or 0)
    model_meta["sha256"] = str(materialized.get("sha256") or "")
    staged_manifest["model"] = model_meta
    manifest_path.write_text(json.dumps(staged_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    if not model_target.exists():
        raise FileNotFoundError(f"固定管家层模型未能复制到发布目录: {model_target}")
    return {
        "model_path": str(model_target),
        "model_size": int(materialized.get("size") or 0),
        "model_sha256": str(materialized.get("sha256") or ""),
        "manifest_path": str(manifest_path),
    }


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


def _resolve_iscc_path() -> Path:
    for candidate in ISCC_CANDIDATES:
        if candidate.exists():
            return candidate
    raise FileNotFoundError("未找到 Inno Setup 编译器 ISCC.exe，无法生成安装界面。")


def _build_setup_installer(stage_dir: Path, release_root: Path, version: str) -> Path:
    if not INSTALLER_SCRIPT.exists():
        raise FileNotFoundError(f"未找到安装器脚本: {INSTALLER_SCRIPT}")
    iscc_path = _resolve_iscc_path()
    command = [
        str(iscc_path),
        f"/DMyAppVersion={version}",
        f"/DReleaseDir={stage_dir}",
        f"/O{release_root}",
        str(INSTALLER_SCRIPT),
    ]
    completed = subprocess.run(
        command,
        cwd=str(INSTALLER_SCRIPT.parent),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode != 0:
        message = completed.stdout.strip() or completed.stderr.strip() or "未知错误"
        raise RuntimeError(f"安装器生成失败：{message}")
    installer_path = release_root / f"NeuroLab-Hub-Setup-v{version}.exe"
    if not installer_path.exists():
        raise FileNotFoundError(f"安装器编译完成，但未找到输出文件: {installer_path}")
    return installer_path


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
    bundled_vosk = _copy_bundled_vosk_assets(stage_dir)
    orchestrator_assets = _materialize_orchestrator_runtime(stage_dir)
    orchestrator_model = _materialize_orchestrator_model(stage_dir)
    asset_manifest = json.loads(Path(orchestrator_model["manifest_path"]).read_text(encoding="utf-8"))

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
        "orchestrator_assets": {
            "runtime": asset_manifest.get("runtime", {}),
            "model": asset_manifest.get("model", {}),
            "staged_runtime_dir": orchestrator_assets["runtime_dir"],
            "staged_manifest_path": orchestrator_assets["manifest_path"],
            "runtime_files": orchestrator_assets["copied_files"],
            "staged_model_path": orchestrator_model["model_path"],
            "staged_model_size": orchestrator_model["model_size"],
            "staged_model_sha256": orchestrator_model["model_sha256"],
        },
        "bundled_speech_assets": {
            "vosk": bundled_vosk,
        },
    }
    manifest_path = _write_manifest(stage_dir, manifest)
    manifest["manifest_path"] = str(manifest_path)

    _zip_stage(stage_dir, zip_path)
    manifest["zip_size"] = zip_path.stat().st_size
    installer_path = _build_setup_installer(stage_dir, release_root, version)
    manifest["setup_path"] = str(installer_path)
    manifest["setup_size"] = installer_path.stat().st_size
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
