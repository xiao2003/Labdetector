#!/usr/bin/env python3
"""Knowledge-base builder for structured/unstructured files."""

import argparse
import json
import os
import shutil
from typing import List

from pcside.knowledge_base.structured_kb import get_default_structured_kb


def collect_files(paths: List[str], allowed) -> List[str]:
    files = []
    for p in paths:
        if os.path.isdir(p):
            for name in sorted(os.listdir(p)):
                full = os.path.join(p, name)
                if os.path.isfile(full) and os.path.splitext(name)[1].lower() in allowed:
                    files.append(full)
            continue
        if os.path.isfile(p) and os.path.splitext(p)[1].lower() in allowed:
            files.append(p)
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description="导入知识库文件（支持 txt/md/csv/json/xls/xlsx）")
    parser.add_argument("paths", nargs="+", help="文件或目录路径")
    parser.add_argument("--dry-run", action="store_true", help="仅扫描，不实际导入")
    parser.add_argument("--reset-index", action="store_true", help="导入前清空向量库索引")
    parser.add_argument("--report", default="", help="导出导入报告 JSON 路径")
    parser.add_argument("--structured", action="store_true", help="同步构建结构化SQLite知识库")
    args = parser.parse_args()

    allowed = {".txt", ".md", ".csv", ".json", ".xls", ".xlsx"}
    candidates = collect_files(args.paths, allowed)
    imported = []
    failed = []
    structured_imported = 0

    # lazy load rag engine: allow dry-run / structured-only in lean env.
    rag_engine = None
    if not args.dry_run:
        try:
            from pcside.knowledge_base.rag_engine import rag_engine as _rag_engine

            rag_engine = _rag_engine
            if args.reset_index and os.path.exists(rag_engine.db_path):
                shutil.rmtree(rag_engine.db_path, ignore_errors=True)
                rag_engine._init_db()  # noqa
        except Exception as e:
            print(f"[WARN] RAG 引擎不可用，将跳过向量入库: {e}")

    sk = get_default_structured_kb() if args.structured else None

    for fp in candidates:
        if args.dry_run:
            imported.append(os.path.basename(fp))
            continue

        ok = False
        if rag_engine is not None:
            ok = rag_engine.ingest_knowledge_file(fp)
        else:
            # 没有RAG引擎时，只要结构化库成功也视为导入成功
            ok = sk is not None

        if ok:
            imported.append(os.path.basename(fp))
            if sk is not None:
                structured_imported += sk.import_file(fp)
        else:
            failed.append(os.path.basename(fp))

    summary = {
        "total_candidates": len(candidates),
        "imported_count": len(imported),
        "failed_count": len(failed),
        "imported": imported,
        "failed": failed,
        "dry_run": args.dry_run,
        "structured_enabled": args.structured,
        "structured_records": structured_imported if not args.dry_run else 0,
    }

    if args.report:
        with open(args.report, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
