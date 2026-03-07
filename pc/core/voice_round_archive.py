from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

from pc.app_identity import resource_path


def _timestamp() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


class VoiceRoundArchive:
    def __init__(self, root_dir: Optional[Path] = None) -> None:
        self.root_dir = root_dir or Path(resource_path("pc/log/voice_rounds"))
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._session_id = ""
        self._session_dir: Optional[Path] = None
        self._session_meta: Dict[str, Any] = {}
        self._round_index = 0

    def open_session(self, mode: str, source: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        with self._lock:
            stamp = time.strftime("%Y%m%d_%H%M%S")
            safe_source = source.replace(":", "_")
            self._session_id = f"{stamp}_{mode}_{safe_source}"
            self._session_dir = self.root_dir / self._session_id
            self._session_dir.mkdir(parents=True, exist_ok=True)
            self._round_index = 0
            self._session_meta = {
                "session_id": self._session_id,
                "mode": mode,
                "source": source,
                "opened_at": _timestamp(),
            }
            if metadata:
                self._session_meta.update(metadata)
            self._write_json(self._session_dir / "session.json", self._session_meta)
            self._write_session_markdown(self._session_dir / "session.md", self._session_meta)
            return self._session_id

    def close_session(self) -> None:
        with self._lock:
            if not self._session_dir or not self._session_id:
                return
            summary = dict(self._session_meta)
            summary["closed_at"] = _timestamp()
            summary["round_count"] = self._round_index
            self._write_json(self._session_dir / "session.json", summary)
            self._write_session_markdown(self._session_dir / "session.md", summary)
            self._session_id = ""
            self._session_dir = None
            self._session_meta = {}
            self._round_index = 0

    def ensure_session(self, mode: str, source: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        with self._lock:
            if self._session_dir is not None and self._session_id:
                return self._session_id
        return self.open_session(mode=mode, source=source, metadata=metadata)

    def record_round(self, prompt: str, response: str, source: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        with self._lock:
            self.ensure_session(mode=str((metadata or {}).get("mode") or "adhoc"), source=source, metadata=metadata)
            assert self._session_dir is not None
            self._round_index += 1
            record: Dict[str, Any] = {}
            if metadata:
                record.update(metadata)
            record.update(
                {
                    "session_id": self._session_id,
                    "round_index": self._round_index,
                    "source": source,
                    "prompt": prompt,
                    "response": response,
                    "timestamp": _timestamp(),
                }
            )
            stem = f"round_{self._round_index:03d}"
            self._write_json(self._session_dir / f"{stem}.json", record)
            self._write_markdown(self._session_dir / f"{stem}.md", record)
            self._append_transcript(self._session_dir / "transcript.md", record)
            return record

    @staticmethod
    def _write_json(path: Path, payload: Dict[str, Any]) -> None:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _write_session_markdown(path: Path, payload: Dict[str, Any]) -> None:
        lines = [
            f"# ???? {payload.get('session_id', '')}",
            "",
            f"- ??: {payload.get('mode', '')}",
            f"- ??: {payload.get('source', '')}",
            f"- ????: {payload.get('project_name', '')}",
            f"- ????: {payload.get('experiment_name', '')}",
            f"- ????: {payload.get('operator_name', '')}",
            f"- ??: {', '.join(payload.get('tags') or [])}",
            f"- AI ??: {payload.get('backend', '')}",
            f"- ??: {payload.get('model', '')}",
            f"- ????: {payload.get('opened_at', '')}",
            f"- ????: {payload.get('closed_at', '')}",
            f"- ???: {payload.get('round_count', '')}",
            "",
        ]
        path.write_text("\n".join(lines), encoding="utf-8")

    @staticmethod
    def _write_markdown(path: Path, payload: Dict[str, Any]) -> None:
        lines = [
            f"# ???? {int(payload.get('round_index', 0)):03d}",
            "",
            f"- ??: {payload.get('timestamp', '')}",
            f"- ??: {payload.get('source', '')}",
            f"- ????: {payload.get('mode', '')}",
            f"- ??: {payload.get('node_id', '')}",
            f"- ????: {payload.get('project_name', '')}",
            f"- ????: {payload.get('experiment_name', '')}",
            f"- ????: {payload.get('operator_name', '')}",
            f"- ??: {', '.join(payload.get('tags') or [])}",
            "",
            "## ????",
            str(payload.get("prompt", "")).strip(),
            "",
            "## ????",
            str(payload.get("response", "")).strip(),
            "",
        ]
        path.write_text("\n".join(lines), encoding="utf-8")

    @staticmethod
    def _append_transcript(path: Path, payload: Dict[str, Any]) -> None:
        lines = [
            f"## Round {int(payload.get('round_index', 0)):03d}",
            f"- ??: {payload.get('timestamp', '')}",
            f"- ??: {payload.get('source', '')}",
            f"- ??: {payload.get('project_name', '')}",
            f"- ??: {payload.get('experiment_name', '')}",
            f"- ??: {payload.get('operator_name', '')}",
            "",
            "???",
            str(payload.get("prompt", "")).strip(),
            "",
            "???",
            str(payload.get("response", "")).strip(),
            "",
        ]
        with path.open("a", encoding="utf-8") as handle:
            handle.write("\n".join(lines))


_voice_round_archive: Optional[VoiceRoundArchive] = None


def get_voice_round_archive() -> VoiceRoundArchive:
    global _voice_round_archive
    if _voice_round_archive is None:
        _voice_round_archive = VoiceRoundArchive()
    return _voice_round_archive
