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
        self._rounds: list[Dict[str, Any]] = []

    def open_session(self, mode: str, source: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        with self._lock:
            stamp = time.strftime("%Y%m%d_%H%M%S")
            safe_source = source.replace(":", "_")
            self._session_id = f"{stamp}_{mode}_{safe_source}"
            self._session_dir = self.root_dir / self._session_id
            self._session_dir.mkdir(parents=True, exist_ok=True)
            self._round_index = 0
            self._rounds = []
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
            self._rounds = []

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
            self._rounds.append(record)
            return record

    def write_session_summary(
        self,
        summary_text: str,
        knowledge_items: Optional[list[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[Path]:
        with self._lock:
            if not self._session_dir or not self._session_id:
                return None
            payload = dict(self._session_meta)
            if metadata:
                payload.update(metadata)
            payload.update(
                {
                    "session_id": self._session_id,
                    "generated_at": _timestamp(),
                    "round_count": self._round_index,
                    "summary_text": summary_text,
                    "knowledge_items": list(knowledge_items or []),
                }
            )
            self._write_json(self._session_dir / "session_summary.json", payload)
            self._write_summary_markdown(self._session_dir / "session_summary.md", payload)
            return self._session_dir / "session_summary.md"

    def get_session_rounds(self) -> list[Dict[str, Any]]:
        with self._lock:
            return [dict(item) for item in self._rounds]

    @staticmethod
    def _write_json(path: Path, payload: Dict[str, Any]) -> None:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _write_session_markdown(path: Path, payload: Dict[str, Any]) -> None:
        lines = [
            f"# 语音会话 {payload.get('session_id', '')}",
            "",
            f"- 模式: {payload.get('mode', '')}",
            f"- 来源: {payload.get('source', '')}",
            f"- 实验项目: {payload.get('project_name', '')}",
            f"- 实验名称: {payload.get('experiment_name', '')}",
            f"- 实验人员: {payload.get('operator_name', '')}",
            f"- 标签: {', '.join(payload.get('tags') or [])}",
            f"- AI 后端: {payload.get('backend', '')}",
            f"- 模型: {payload.get('model', '')}",
            f"- 开始时间: {payload.get('opened_at', '')}",
            f"- 结束时间: {payload.get('closed_at', '')}",
            f"- 轮次数: {payload.get('round_count', '')}",
            "",
        ]
        path.write_text("\n".join(lines), encoding="utf-8")

    @staticmethod
    def _write_markdown(path: Path, payload: Dict[str, Any]) -> None:
        lines = [
            f"# 语音轮次 {int(payload.get('round_index', 0)):03d}",
            "",
            f"- 时间: {payload.get('timestamp', '')}",
            f"- 来源: {payload.get('source', '')}",
            f"- 运行模式: {payload.get('mode', '')}",
            f"- 节点: {payload.get('node_id', '')}",
            f"- 实验项目: {payload.get('project_name', '')}",
            f"- 实验名称: {payload.get('experiment_name', '')}",
            f"- 实验人员: {payload.get('operator_name', '')}",
            f"- 标签: {', '.join(payload.get('tags') or [])}",
            "",
            "## 用户提问",
            str(payload.get("prompt", "")).strip(),
            "",
            "## 模型回答",
            str(payload.get("response", "")).strip(),
            "",
        ]
        path.write_text("\n".join(lines), encoding="utf-8")

    @staticmethod
    def _append_transcript(path: Path, payload: Dict[str, Any]) -> None:
        lines = [
            f"## Round {int(payload.get('round_index', 0)):03d}",
            f"- 时间: {payload.get('timestamp', '')}",
            f"- 来源: {payload.get('source', '')}",
            f"- 项目: {payload.get('project_name', '')}",
            f"- 实验: {payload.get('experiment_name', '')}",
            f"- 人员: {payload.get('operator_name', '')}",
            "",
            "用户提问",
            str(payload.get("prompt", "")).strip(),
            "",
            "模型回答",
            str(payload.get("response", "")).strip(),
            "",
        ]
        with path.open("a", encoding="utf-8") as handle:
            handle.write("\n".join(lines))

    @staticmethod
    def _write_summary_markdown(path: Path, payload: Dict[str, Any]) -> None:
        knowledge_items = list(payload.get("knowledge_items") or [])
        lines = [
            f"# 语音会话总结 {payload.get('session_id', '')}",
            "",
            f"- 生成时间: {payload.get('generated_at', '')}",
            f"- 轮次数: {payload.get('round_count', 0)}",
            "",
            "## 会话摘要",
            str(payload.get("summary_text", "")).strip(),
            "",
            "## 提取的有效知识",
        ]
        if knowledge_items:
            lines.extend(f"- {item}" for item in knowledge_items)
        else:
            lines.append("- 无明确可回灌知识")
        path.write_text("\n".join(lines), encoding="utf-8")


_voice_round_archive: Optional[VoiceRoundArchive] = None


def get_voice_round_archive() -> VoiceRoundArchive:
    global _voice_round_archive
    if _voice_round_archive is None:
        _voice_round_archive = VoiceRoundArchive()
    return _voice_round_archive
