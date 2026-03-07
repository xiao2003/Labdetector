from __future__ import annotations

import json
import os
import shutil
import time
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

TEXT_EXTENSIONS = {".txt", ".md", ".csv", ".json", ".xls", ".xlsx"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg"}
VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".wmv", ".webm"}
ALL_IMPORTABLE_EXTENSIONS = TEXT_EXTENSIONS | IMAGE_EXTENSIONS | AUDIO_EXTENSIONS | VIDEO_EXTENSIONS


@dataclass
class PreparedKnowledgeAsset:
    source_name: str
    source_type: str
    archived_paths: List[str]
    index_path: str


def _safe_copy(source: Path, target_dir: Path) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / source.name
    if source.resolve() == target.resolve():
        return target
    if target.exists():
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        target = target_dir / f"{target.stem}_{timestamp}{target.suffix}"
    shutil.copy2(str(source), str(target))
    return target


def _file_size_text(path: Path) -> str:
    size = path.stat().st_size
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    if size < 1024 * 1024 * 1024:
        return f"{size / 1024 / 1024:.1f} MB"
    return f"{size / 1024 / 1024 / 1024:.2f} GB"


def _probe_image(source: Path) -> Dict[str, str]:
    try:
        from PIL import Image

        with Image.open(source) as image:
            width, height = image.size
        return {"resolution": f"{width}x{height}"}
    except Exception:
        return {}


def _probe_audio(source: Path) -> Dict[str, str]:
    if source.suffix.lower() == ".wav":
        try:
            with wave.open(str(source), "rb") as handle:
                frames = handle.getnframes()
                rate = handle.getframerate() or 1
                duration = frames / float(rate)
                channels = handle.getnchannels()
                return {
                    "duration_seconds": f"{duration:.2f}",
                    "channels": str(channels),
                    "sample_rate": str(rate),
                }
        except Exception:
            return {}
    return {}


def _probe_video(source: Path) -> Dict[str, str]:
    try:
        import cv2

        capture = cv2.VideoCapture(str(source))
        if not capture.isOpened():
            capture.release()
            return {}
        fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
        frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        capture.release()
        duration = (frames / fps) if fps > 0 else 0.0
        result = {
            "resolution": f"{width}x{height}" if width and height else "",
            "frame_count": str(frames) if frames else "",
            "fps": f"{fps:.2f}" if fps else "",
            "duration_seconds": f"{duration:.2f}" if duration else "",
        }
        return {key: value for key, value in result.items() if value}
    except Exception:
        return {}


def _build_media_markdown(source: Path, scope_title: str, source_type: str, metadata: Dict[str, str]) -> str:
    lines = [
        "# 媒体知识条目",
        "",
        f"- 来源文件: {source.name}",
        f"- 文件类型: {source_type}",
        f"- 适用知识库: {scope_title}",
        f"- 导入时间: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 文件大小: {_file_size_text(source)}",
    ]
    for key, value in metadata.items():
        if value:
            lines.append(f"- {key}: {value}")
    lines.extend(
        [
            "",
            "## 自动摘要",
            "该条目由软件自动从原始媒体文件生成，用于建立可检索的知识索引。",
            "如需更高质量的知识问答，建议同时导入对应的实验记录、字幕稿、SOP、说明书或人工整理文本。",
            "",
            "## 适用方式",
            "1. 作为公共背景知识库中的实验素材索引。",
            "2. 作为对应专家知识库中的案例、样本或演示资料。",
            "3. 与文本说明一起导入时，可显著提升问答与规则检索效果。",
        ]
    )
    return "\n".join(lines)


def prepare_knowledge_asset(source_path: str, docs_dir: Path, scope_title: str) -> PreparedKnowledgeAsset:
    source = Path(source_path)
    if not source.exists() or not source.is_file():
        raise FileNotFoundError(source_path)

    extension = source.suffix.lower()
    if extension not in ALL_IMPORTABLE_EXTENSIONS:
        raise ValueError(f"暂不支持的知识文件格式: {extension}")

    docs_dir.mkdir(parents=True, exist_ok=True)
    if extension in TEXT_EXTENSIONS:
        archived = _safe_copy(source, docs_dir)
        return PreparedKnowledgeAsset(
            source_name=source.name,
            source_type="text",
            archived_paths=[str(archived)],
            index_path=str(archived),
        )

    media_dir = docs_dir / "media"
    generated_dir = docs_dir / "generated"
    archived_media = _safe_copy(source, media_dir)

    metadata: Dict[str, str] = {}
    source_type = "image"
    if extension in IMAGE_EXTENSIONS:
        metadata = _probe_image(archived_media)
        source_type = "image"
    elif extension in AUDIO_EXTENSIONS:
        metadata = _probe_audio(archived_media)
        source_type = "audio"
    elif extension in VIDEO_EXTENSIONS:
        metadata = _probe_video(archived_media)
        source_type = "video"

    note_name = f"{archived_media.stem}_knowledge.md"
    note_path = generated_dir / note_name
    note_path.parent.mkdir(parents=True, exist_ok=True)
    note_path.write_text(
        _build_media_markdown(archived_media, scope_title, source_type, metadata),
        encoding="utf-8",
    )
    manifest_path = generated_dir / f"{archived_media.stem}_knowledge.json"
    manifest_path.write_text(
        json.dumps(
            {
                "source_name": source.name,
                "source_type": source_type,
                "scope_title": scope_title,
                "archived_media": str(archived_media),
                "generated_note": str(note_path),
                "metadata": metadata,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return PreparedKnowledgeAsset(
        source_name=source.name,
        source_type=source_type,
        archived_paths=[str(archived_media), str(note_path), str(manifest_path)],
        index_path=str(note_path),
    )
