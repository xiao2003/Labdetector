from __future__ import annotations

import json
import time
import wave
from pathlib import Path
from typing import Any, Dict, Iterable, List


def iter_wav_chunks(wav_path: str | Path, chunk_frames: int = 4000) -> Iterable[bytes]:
    source = Path(wav_path)
    with wave.open(str(source), "rb") as reader:
        if reader.getnchannels() != 1 or reader.getsampwidth() != 2 or reader.getframerate() != 16000:
            raise ValueError(f"音频格式不符合要求: {source}")
        while True:
            payload = reader.readframes(chunk_frames)
            if not payload:
                break
            yield payload


def replay_voice_plan(
    *,
    recognizer_cls,
    interaction_cls,
    model_path: str,
    wake_word: str,
    sample_plan: List[Dict[str, Any]],
    chunk_frames: int = 4000,
) -> Dict[str, Any]:
    recognizer = recognizer_cls(model_path)
    interaction = interaction_cls(recognizer, wake_word=wake_word)
    records: List[Dict[str, Any]] = []
    outgoing: List[Dict[str, str]] = []

    for item in sample_plan:
        sample_path = str(item.get("path") or "").strip()
        sample_id = str(item.get("sample_id") or Path(sample_path).stem)
        item_records: List[Dict[str, Any]] = []
        emitted: List[str] = []
        for chunk in iter_wav_chunks(sample_path, chunk_frames=chunk_frames):
            event = interaction.process_audio(chunk)
            if not event:
                continue
            emitted.append(event)
            row: Dict[str, Any] = {"event": event}
            if event == "EVENT:WOKEN":
                outgoing.append({"kind": "woken", "payload": "PI_EVENT:WOKEN"})
            elif event.startswith("CMD_TEXT:"):
                text = event.replace("CMD_TEXT:", "", 1)
                row["recognized_text"] = text
                outgoing.append({"kind": "voice_command", "payload": f"PI_VOICE_COMMAND:{text}"})
                interaction.is_active = False
            item_records.append(row)
        final_text = ""
        if hasattr(recognizer, "get_final_text"):
            try:
                final_text = str(recognizer.get_final_text() or "").strip()
            except Exception:
                final_text = ""
        if final_text:
            flushed = _flush_final_text(interaction, final_text)
            if flushed:
                emitted.append(flushed)
                row = {"event": flushed}
                if flushed == "EVENT:WOKEN":
                    outgoing.append({"kind": "woken", "payload": "PI_EVENT:WOKEN"})
                elif flushed.startswith("CMD_TEXT:"):
                    text = flushed.replace("CMD_TEXT:", "", 1)
                    row["recognized_text"] = text
                    outgoing.append({"kind": "voice_command", "payload": f"PI_VOICE_COMMAND:{text}"})
                    interaction.is_active = False
                item_records.append(row)
        recognized_texts = [row.get("recognized_text", "") for row in item_records if row.get("recognized_text")]
        records.append(
            {
                "sample_id": sample_id,
                "path": sample_path,
                "speaker_type": str(item.get("speaker_type") or ""),
                "category": str(item.get("category") or ""),
                "text": str(item.get("text") or ""),
                "expected_keywords": list(item.get("expected_keywords") or []),
                "emitted": emitted,
                "recognized_texts": recognized_texts,
                "keyword_match": _keyword_match(recognized_texts, list(item.get("expected_keywords") or [])),
                "processed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
        )

    return {
        "records": records,
        "outgoing_messages": outgoing,
        "summary": {
            "sample_count": len(sample_plan),
            "command_count": len([row for row in outgoing if row["kind"] == "voice_command"]),
            "wake_count": len([row for row in outgoing if row["kind"] == "woken"]),
        },
    }


def _keyword_match(recognized_texts: List[str], expected_keywords: List[str]) -> bool:
    if not expected_keywords:
        return bool(recognized_texts)
    normalized = "".join(recognized_texts).replace(" ", "")
    return all(str(keyword or "").replace(" ", "") in normalized for keyword in expected_keywords)


def _flush_final_text(interaction, final_text: str) -> str | None:
    normalized = str(final_text or "").replace(" ", "")
    if not normalized:
        return None
    wake_word = str(getattr(interaction, "wake_word", "") or "").replace(" ", "")
    is_active = bool(getattr(interaction, "is_active", False))
    if not is_active and wake_word and wake_word in normalized:
        interaction.is_active = True
        interaction.last_wake_time = time.time()
        return "EVENT:WOKEN"
    if is_active:
        return f"CMD_TEXT:{normalized}"
    return None


def serialize_audio_records(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)
