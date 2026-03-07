from __future__ import annotations

import contextlib
import wave
from pathlib import Path
from typing import Dict

import cv2
from PIL import Image


def _safe_float(value: float | int) -> str:
    try:
        return f"{float(value):.2f}"
    except Exception:
        return "0.00"


def describe_image(path: str | Path) -> Dict[str, str]:
    source = Path(path)
    summary = {
        "media_type": "image",
        "semantic_summary": f"图片资料 {source.name}",
        "keywords": "image,knowledge",
    }
    try:
        with Image.open(source) as image:
            width, height = image.size
            summary.update(
                {
                    "width": str(width),
                    "height": str(height),
                    "mode": str(image.mode),
                    "semantic_summary": f"图片资料 {source.name}，尺寸 {width}x{height}，可作为实验场景、器具外观或流程截图素材。",
                    "keywords": f"image,{image.mode.lower()},visual",
                }
            )
    except Exception:
        pass
    return summary


def describe_audio(path: str | Path) -> Dict[str, str]:
    source = Path(path)
    summary = {
        "media_type": "audio",
        "semantic_summary": f"音频资料 {source.name}",
        "keywords": "audio,voice,knowledge",
    }
    with contextlib.suppress(Exception):
        with wave.open(str(source), "rb") as handle:
            frames = handle.getnframes()
            rate = handle.getframerate() or 1
            duration = frames / float(rate)
            summary.update(
                {
                    "channels": str(handle.getnchannels()),
                    "sample_rate": str(rate),
                    "duration_seconds": _safe_float(duration),
                    "semantic_summary": f"音频资料 {source.name}，时长 {duration:.1f} 秒，可作为语音问答、播报或实验语音样本。",
                    "keywords": "audio,voice,speech,knowledge",
                }
            )
    return summary


def describe_video(path: str | Path) -> Dict[str, str]:
    source = Path(path)
    summary = {
        "media_type": "video",
        "semantic_summary": f"视频资料 {source.name}",
        "keywords": "video,frame,knowledge",
    }
    cap = cv2.VideoCapture(str(source))
    try:
        if cap.isOpened():
            frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
            duration = frames / fps if fps > 0 else 0.0
            summary.update(
                {
                    "frame_count": str(frames),
                    "fps": _safe_float(fps),
                    "width": str(width),
                    "height": str(height),
                    "duration_seconds": _safe_float(duration),
                    "semantic_summary": f"视频资料 {source.name}，分辨率 {width}x{height}，时长 {duration:.1f} 秒，可用于流程复盘、关键帧抽取和行为分析。",
                    "keywords": "video,frame,timeline,procedure,knowledge",
                }
            )
    finally:
        cap.release()
    return summary


def describe_media(path: str | Path) -> Dict[str, str]:
    source = Path(path)
    suffix = source.suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".bmp", ".webp"}:
        return describe_image(source)
    if suffix in {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg"}:
        return describe_audio(source)
    if suffix in {".mp4", ".avi", ".mov", ".mkv", ".wmv", ".webm"}:
        return describe_video(source)
    return {
        "media_type": "file",
        "semantic_summary": f"通用资料 {source.name}",
        "keywords": "file,knowledge",
    }
