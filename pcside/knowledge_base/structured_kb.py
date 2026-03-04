"""Structured knowledge base (SQLite) for fast rule lookup.

Supports importing CSV/JSON/TXT/MD/(optional) XLSX to a normalized table.
"""

from __future__ import annotations

import csv
import json
import os
import sqlite3
from dataclasses import dataclass
from typing import Dict, Iterable, List


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

    def _init_db(self):
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

    def upsert_records(self, records: Iterable[KBRecord]):
        rows = [(r.category, r.name, r.value, r.source) for r in records]
        self.conn.executemany(
            "INSERT INTO kb_records(category,name,value,source) VALUES(?,?,?,?)",
            rows,
        )
        self.conn.commit()

    def import_file(self, path: str) -> int:
        ext = os.path.splitext(path)[1].lower()
        src = os.path.basename(path)
        records: List[KBRecord] = []

        if ext in {".txt", ".md"}:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read().strip()
            if content:
                records.append(KBRecord("document", src, content[:8000], src))

        elif ext == ".json":
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                for k, v in data.items():
                    records.append(KBRecord("json", str(k), json.dumps(v, ensure_ascii=False), src))
            elif isinstance(data, list):
                for idx, item in enumerate(data):
                    records.append(KBRecord("json_list", f"{src}#{idx}", json.dumps(item, ensure_ascii=False), src))

        elif ext == ".csv":
            with open(path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if not row:
                        continue
                    name = str(row.get("name") or row.get("化学品") or row.get("title") or src)
                    value = json.dumps(row, ensure_ascii=False)
                    records.append(KBRecord("csv", name, value, src))

        elif ext in {".xlsx", ".xls"}:
            try:
                import pandas as pd  # type: ignore

                sheets = pd.read_excel(path, sheet_name=None)
                for sheet_name, df in sheets.items():
                    for _, row in df.iterrows():
                        row_dict = {k: ("" if str(v) == "nan" else str(v)) for k, v in row.to_dict().items()}
                        name = row_dict.get("name") or row_dict.get("化学品") or f"{src}:{sheet_name}"
                        records.append(KBRecord("excel", str(name), json.dumps(row_dict, ensure_ascii=False), src))
            except Exception:
                pass

        self.upsert_records(records)
        return len(records)

    def search(self, keyword: str, limit: int = 5) -> List[Dict[str, str]]:
        cur = self.conn.execute(
            """
            SELECT category, name, value, source
            FROM kb_records
            WHERE name LIKE ? OR value LIKE ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (f"%{keyword}%", f"%{keyword}%", limit),
        )
        cols = ["category", "name", "value", "source"]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


def get_default_structured_kb() -> StructuredKnowledgeBase:
    base = os.path.dirname(os.path.abspath(__file__))
    return StructuredKnowledgeBase(os.path.join(base, "structured_kb.sqlite3"))
