"""Structured knowledge base (SQLite) for fast rule lookup."""

from __future__ import annotations

import csv
import json
import os
import sqlite3
from dataclasses import dataclass
from typing import Dict, Iterable, List

from pc.app_identity import resource_path


@dataclass
class KBRecord:
    category: str
    name: str
    value: str
    source: str


class StructuredKnowledgeBase:
    def __init__(self, db_path: str):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self._init_db()

    def _init_db(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS kb_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT,
                name TEXT,
                value TEXT,
                source TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_kb_name ON kb_records(name)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_kb_category ON kb_records(category)")
        self.conn.commit()

    def upsert_records(self, records: Iterable[KBRecord]) -> None:
        rows = [(record.category, record.name, record.value, record.source) for record in records]
        self.conn.executemany(
            "INSERT INTO kb_records(category,name,value,source) VALUES(?,?,?,?)",
            rows,
        )
        self.conn.commit()

    def import_file(self, path: str) -> int:
        ext = os.path.splitext(path)[1].lower()
        source_name = os.path.basename(path)
        records: List[KBRecord] = []

        if ext in {".txt", ".md"}:
            with open(path, "r", encoding="utf-8") as handle:
                content = handle.read().strip()
            if content:
                records.append(KBRecord("document", source_name, content[:8000], source_name))

        elif ext == ".json":
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, dict):
                for key, value in data.items():
                    records.append(KBRecord("json", str(key), json.dumps(value, ensure_ascii=False), source_name))
            elif isinstance(data, list):
                for index, item in enumerate(data):
                    records.append(KBRecord("json_list", f"{source_name}#{index}", json.dumps(item, ensure_ascii=False), source_name))

        elif ext == ".csv":
            with open(path, "r", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                for row in reader:
                    if not row:
                        continue
                    name = str(
                        row.get("name")
                        or row.get("名称")
                        or row.get("化学品")
                        or row.get("title")
                        or source_name
                    )
                    records.append(KBRecord("csv", name, json.dumps(row, ensure_ascii=False), source_name))

        elif ext in {".xlsx", ".xls"}:
            try:
                import pandas as pd  # type: ignore

                sheets = pd.read_excel(path, sheet_name=None)
                for sheet_name, dataframe in sheets.items():
                    for _, row in dataframe.iterrows():
                        row_dict = {key: ("" if str(value) == "nan" else str(value)) for key, value in row.to_dict().items()}
                        name = row_dict.get("name") or row_dict.get("名称") or row_dict.get("化学品") or f"{source_name}:{sheet_name}"
                        records.append(KBRecord("excel", str(name), json.dumps(row_dict, ensure_ascii=False), source_name))
            except Exception:
                pass

        self.upsert_records(records)
        return len(records)

    def search(self, keyword: str, limit: int = 5) -> List[Dict[str, str]]:
        cursor = self.conn.execute(
            """
            SELECT category, name, value, source
            FROM kb_records
            WHERE name LIKE ? OR value LIKE ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (f"%{keyword}%", f"%{keyword}%", limit),
        )
        columns = ["category", "name", "value", "source"]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]


def get_default_structured_kb() -> StructuredKnowledgeBase:
    return StructuredKnowledgeBase(str(resource_path("pc/knowledge_base/structured_kb.sqlite3")))
