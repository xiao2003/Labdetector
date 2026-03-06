#!/usr/bin/env python3
"""Knowledge-base builder for public and expert-scoped knowledge bases."""

from __future__ import annotations

import argparse
import json
from typing import List

from pcside.knowledge_base.rag_engine import knowledge_manager


def main() -> int:
    parser = argparse.ArgumentParser(description="导入知识库文件（支持 txt/md/csv/json/xls/xlsx）")
    parser.add_argument("paths", nargs="*", help="文件或目录路径")
    parser.add_argument("--scope", default="common", help="知识库作用域，默认 common")
    parser.add_argument("--expert", default="", help="专家模块名，等价于 --scope expert.<module>")
    parser.add_argument("--reset-index", action="store_true", help="导入前清空当前作用域索引")
    parser.add_argument("--report", default="", help="导出导入报告 JSON 路径")
    parser.add_argument("--no-structured", action="store_true", help="仅构建向量知识库，不构建结构化库")
    parser.add_argument("--list-scopes", action="store_true", help="列出公共库和专家库作用域")
    args = parser.parse_args()

    if args.list_scopes:
        rows = knowledge_manager.list_scopes(include_known_experts=True)
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0

    scope = f"expert.{args.expert}" if args.expert else args.scope
    if not args.paths:
        parser.error("请至少提供一个文件或目录路径，或使用 --list-scopes")

    summary = knowledge_manager.import_paths(
        args.paths,
        scope_name=scope,
        reset_index=args.reset_index,
        structured=not args.no_structured,
    )

    if args.report:
        with open(args.report, "w", encoding="utf-8") as handle:
            json.dump(summary, handle, ensure_ascii=False, indent=2)

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["failed_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
