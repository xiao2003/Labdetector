from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from pc.knowledge_base.rag_engine import knowledge_manager


class KnowledgeCatalogOrderTests(unittest.TestCase):
    def test_list_scopes_prioritizes_newest_docs_in_catalog_preview(self) -> None:
        temp_root = Path(tempfile.mkdtemp(prefix="neurolab_kb_catalog_"))
        original_base = knowledge_manager.base_dir
        original_scopes_root = knowledge_manager.scopes_root
        try:
            knowledge_manager.base_dir = temp_root
            knowledge_manager.scopes_root = temp_root / "scopes"
            knowledge_manager.scopes_root.mkdir(parents=True, exist_ok=True)

            docs_dir, _db_path, _structured_path = knowledge_manager._scope_dirs("expert.safety.chem_safety_expert")
            docs_dir.mkdir(parents=True, exist_ok=True)

            old_doc = docs_dir / "alpha_old.txt"
            new_doc = docs_dir / "chem_release_test.txt"
            old_doc.write_text("old", encoding="utf-8")
            time.sleep(0.02)
            new_doc.write_text("new", encoding="utf-8")

            rows = knowledge_manager.list_scopes(include_known_experts=False)
            row = next(item for item in rows if item["scope"] == "expert.safety.chem_safety_expert")

            self.assertGreaterEqual(int(row["doc_count"]), 2)
            self.assertTrue(row["docs"], "知识目录预览为空")
            self.assertEqual("chem_release_test.txt", row["docs"][0])
        finally:
            knowledge_manager.base_dir = original_base
            knowledge_manager.scopes_root = original_scopes_root


if __name__ == "__main__":
    unittest.main()
