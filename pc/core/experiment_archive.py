from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from pc.app_identity import resource_path


def _timestamp() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


class ExperimentArchive:
    def __init__(self, root_dir: Optional[Path] = None) -> None:
        self.root_dir = root_dir or Path(resource_path("pc/log/experiment_archives"))
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._session_id = ""
        self._session_dir: Optional[Path] = None
        self._session_meta: Dict[str, Any] = {}
        self._event_index = 0

    def open_session(self, metadata: Optional[Dict[str, Any]] = None) -> str:
        with self._lock:
            meta = dict(metadata or {})
            stamp = time.strftime("%Y%m%d_%H%M%S")
            project_name = str(meta.get("project_name") or "lab_project").strip() or "lab_project"
            slug = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in project_name.lower())[:48] or "lab_project"
            self._session_id = f"{stamp}_{slug}"
            self._session_dir = self.root_dir / self._session_id
            self._session_dir.mkdir(parents=True, exist_ok=True)
            (self._session_dir / "events").mkdir(parents=True, exist_ok=True)
            self._event_index = 0
            self._session_meta = {
                "session_id": self._session_id,
                "opened_at": _timestamp(),
                "project_name": meta.get("project_name", ""),
                "experiment_name": meta.get("experiment_name", ""),
                "operator_name": meta.get("operator_name", ""),
                "tags": list(meta.get("tags") or []),
                "mode": meta.get("mode", ""),
                "source": meta.get("source", ""),
                "backend": meta.get("backend", ""),
                "model": meta.get("model", ""),
                "notes": meta.get("notes", ""),
            }
            self._write_json(self._session_dir / "session.json", self._session_meta)
            self._write_markdown(self._session_dir / "summary.md", self._session_meta, [])
            return self._session_id

    def close_session(self) -> None:
        with self._lock:
            if not self._session_dir or not self._session_id:
                return
            summary = dict(self._session_meta)
            summary["closed_at"] = _timestamp()
            summary["event_count"] = self._event_index
            events = self._load_all_events_locked()
            self._write_json(self._session_dir / "session.json", summary)
            self._write_markdown(self._session_dir / "summary.md", summary, events)
            self._session_id = ""
            self._session_dir = None
            self._session_meta = {}
            self._event_index = 0

    def ensure_session(self, metadata: Optional[Dict[str, Any]] = None) -> str:
        with self._lock:
            if self._session_id and self._session_dir is not None:
                return self._session_id
        return self.open_session(metadata=metadata)

    def record_event(self, event_type: str, payload: Dict[str, Any], title: str = "") -> Dict[str, Any]:
        with self._lock:
            self.ensure_session(metadata=payload)
            assert self._session_dir is not None
            self._event_index += 1
            event = {
                "session_id": self._session_id,
                "event_index": self._event_index,
                "event_type": event_type,
                "title": title or event_type,
                "timestamp": _timestamp(),
                "payload": payload,
            }
            event_path = self._session_dir / "events" / f"event_{self._event_index:04d}_{event_type}.json"
            self._write_json(event_path, event)
            return event

    def list_sessions(self, limit: int = 50) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        if not self.root_dir.exists():
            return rows
        for session_dir in sorted(self.root_dir.iterdir(), reverse=True):
            if not session_dir.is_dir():
                continue
            meta_path = session_dir / "session.json"
            if not meta_path.exists():
                continue
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            meta["path"] = str(session_dir)
            meta["event_count"] = meta.get("event_count", len(list((session_dir / "events").glob("*.json"))))
            rows.append(meta)
            if len(rows) >= limit:
                break
        return rows

    def get_session_detail(self, session_id: str) -> Dict[str, Any]:
        session_dir = self.root_dir / session_id
        meta_path = session_dir / "session.json"
        if not meta_path.exists():
            raise FileNotFoundError(f"实验档案不存在: {session_id}")
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        events = []
        for item in sorted((session_dir / "events").glob("*.json")):
            try:
                events.append(json.loads(item.read_text(encoding="utf-8")))
            except Exception:
                continue
        return {
            "session": meta,
            "events": events,
            "path": str(session_dir),
            "summary_path": str(session_dir / "summary.md"),
        }

    def _load_all_events_locked(self) -> List[Dict[str, Any]]:
        if self._session_dir is None:
            return []
        rows = []
        for item in sorted((self._session_dir / "events").glob("*.json")):
            try:
                rows.append(json.loads(item.read_text(encoding="utf-8")))
            except Exception:
                continue
        return rows

    @staticmethod
    def _write_json(path: Path, payload: Dict[str, Any]) -> None:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _write_markdown(path: Path, meta: Dict[str, Any], events: List[Dict[str, Any]]) -> None:
        lines = [
            f"# 实验档案 {meta.get('session_id', '')}",
            "",
            f"- 实验项目: {meta.get('project_name', '')}",
            f"- 实验名称: {meta.get('experiment_name', '')}",
            f"- 实验人员: {meta.get('operator_name', '')}",
            f"- 标签: {', '.join(meta.get('tags') or [])}",
            f"- 模式: {meta.get('mode', '')}",
            f"- 来源: {meta.get('source', '')}",
            f"- AI 后端: {meta.get('backend', '')}",
            f"- 模型: {meta.get('model', '')}",
            f"- 开始时间: {meta.get('opened_at', '')}",
            f"- 结束时间: {meta.get('closed_at', '')}",
            f"- 事件数: {meta.get('event_count', len(events))}",
            "",
            "## 事件记录",
            "",
        ]
        if events:
            for item in events:
                payload = item.get("payload") or {}
                lines.extend([
                    f"### {int(item.get('event_index', 0)):04d} {item.get('title', item.get('event_type', ''))}",
                    f"- 时间: {item.get('timestamp', '')}",
                    f"- 类型: {item.get('event_type', '')}",
                    f"- 内容: {json.dumps(payload, ensure_ascii=False)}",
                    "",
                ])
        else:
            lines.append("当前会话尚无事件记录。")
        path.write_text("\n".join(lines), encoding="utf-8")


_experiment_archive: Optional[ExperimentArchive] = None


def get_experiment_archive() -> ExperimentArchive:
    global _experiment_archive
    if _experiment_archive is None:
        _experiment_archive = ExperimentArchive()
    return _experiment_archive
