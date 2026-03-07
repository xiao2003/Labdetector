from __future__ import annotations

import json
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict

from pc.knowledge_base.media_semantics import describe_media


TEXT_EXTENSIONS = {".txt", ".md", ".csv", ".json", ".xls", ".xlsx"}
MEDIA_EXTENSIONS = {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".mp4", ".avi", ".mov", ".mkv", ".wmv", ".webm", ".jpg", ".jpeg", ".png", ".bmp", ".webp"}
ALL_IMPORTABLE_EXTENSIONS = TEXT_EXTENSIONS | MEDIA_EXTENSIONS


@dataclass
class PreparedKnowledgeAsset:
    source_name: str
    source_path: str
    source_type: str
    asset_path: str
    index_path: str
    manifest_path: str


def _safe_copy(source: Path, target_dir: Path) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / source.name
    if target.exists():
        stem = source.stem
        suffix = source.suffix
        target = target_dir / f"{stem}_{int(time.time())}{suffix}"
    shutil.copy2(source, target)
    return target


def _build_media_markdown(source: Path, scope_title: str, metadata: Dict[str, str]) -> str:
    lines = [
        f"# {scope_title} 媒体资料",
        "",
        f"- 文件名: {source.name}",
        f"- 类型: {metadata.get('media_type', 'file')}",
        f"- 语义摘要: {metadata.get('semantic_summary', '')}",
        f"- 关键词: {metadata.get('keywords', '')}",
        "",
        "## 元数据",
        "",
    ]
    for key, value in metadata.items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## 后续建议", "", "后续可在此基础上继续补充 OCR、ASR、关键帧摘要和结构化知识抽取结果。", ""])
    return "\n".join(lines)


def prepare_knowledge_asset(source_path: str, docs_dir: Path, scope_title: str) -> PreparedKnowledgeAsset:
    source = Path(source_path).expanduser().resolve()
    if not source.exists():
        raise FileNotFoundError(f"知识资料不存在: {source}")

    asset_root = docs_dir / "assets"
    asset_path = _safe_copy(source, asset_root)
    metadata = describe_media(asset_path)
    metadata.update(
        {
            "original_path": str(source),
            "stored_path": str(asset_path),
            "scope_title": scope_title,
            "ingested_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
    )

    stem = asset_path.stem
    index_path = docs_dir / f"{stem}.md"
    manifest_path = docs_dir / f"{stem}.media.json"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(_build_media_markdown(asset_path, scope_title, metadata), encoding="utf-8")
    manifest_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    return PreparedKnowledgeAsset(
        source_name=source.name,
        source_path=str(source),
        source_type=str(metadata.get("media_type", "file")),
        asset_path=str(asset_path),
        index_path=str(index_path),
        manifest_path=str(manifest_path),
    )
