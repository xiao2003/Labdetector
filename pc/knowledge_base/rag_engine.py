from __future__ import annotations

import importlib
import json
import logging
import os
import shutil
import threading
import time
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from pc.app_identity import resource_path
from pc.core.expert_registry import known_scopes, scope_title
from pc.core.logger import console_error, console_info
from pc.knowledge_base.media_ingestion import (
    ALL_IMPORTABLE_EXTENSIONS,
    TEXT_EXTENSIONS,
    prepare_knowledge_asset,
)
from pc.knowledge_base.structured_kb import StructuredKnowledgeBase, get_default_structured_kb

os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["TRANSFORMERS_VERBOSITY"] = "error"
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("sentence_transformers").setLevel(logging.WARNING)
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)


class ScopedRAGEngine:
    SUPPORTED_EXTENSIONS = set(ALL_IMPORTABLE_EXTENSIONS)
    _shared_embeddings = None
    _vector_components: Optional[Tuple[object, object, object, object]] = None
    _vector_import_failed = False

    def __init__(self, scope_name: str, docs_dir: Path, db_path: Path, title: str = ""):
        self.scope_name = scope_name
        self.title = title or scope_name
        self.docs_dir = docs_dir
        self.db_path = db_path
        self.docs_dir.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.vector_db = None
        self._init_db()

    @classmethod
    def _load_vector_components(cls) -> Optional[Tuple[object, object, object, object]]:
        if cls._vector_components is not None:
            return cls._vector_components
        if cls._vector_import_failed:
            return None
        try:
            faiss_module = importlib.import_module("langchain_community.vectorstores")
            documents_module = importlib.import_module("langchain_core.documents")
            embeddings_module = importlib.import_module("langchain_huggingface")
            splitters_module = importlib.import_module("langchain_text_splitters")
            cls._vector_components = (
                getattr(faiss_module, "FAISS"),
                getattr(documents_module, "Document"),
                getattr(embeddings_module, "HuggingFaceEmbeddings"),
                getattr(splitters_module, "RecursiveCharacterTextSplitter"),
            )
            return cls._vector_components
        except Exception:
            cls._vector_import_failed = True
            return None

    @classmethod
    def _get_embeddings(cls):
        components = cls._load_vector_components()
        if components is None:
            return None
        if cls._shared_embeddings is not None:
            return cls._shared_embeddings
        _, _, embeddings_cls, _ = components
        try:
            console_info("正在加载轻量向量检索组件，首次初始化可能需要数十秒。")
            cls._shared_embeddings = embeddings_cls(model_name="shibing624/text2vec-base-chinese")
            return cls._shared_embeddings
        except Exception as exc:
            console_error(f"向量检索组件初始化失败，已回退为轻量文本检索: {exc}")
            cls._vector_import_failed = True
            return None

    def _init_db(self) -> None:
        components = self._load_vector_components()
        embeddings = self._get_embeddings()
        if components is None or embeddings is None:
            self.vector_db = None
            return
        faiss_cls, _, _, _ = components
        try:
            if self.db_path.exists():
                self.vector_db = faiss_cls.load_local(
                    str(self.db_path),
                    embeddings,
                    allow_dangerous_deserialization=True,
                )
                return
            self.vector_db = faiss_cls.from_texts(["知识库初始化完成"], embeddings)
            self.vector_db.save_local(str(self.db_path))
        except Exception as exc:
            console_error(f"向量索引加载失败，已回退为轻量文本检索: {exc}")
            self.vector_db = None

    def reset_index(self) -> None:
        if self.db_path.exists():
            shutil.rmtree(self.db_path, ignore_errors=True)
        self._init_db()

    def _read_text_content(self, filepath: str) -> str:
        ext = os.path.splitext(filepath)[1].lower()
        if ext == ".json":
            with open(filepath, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            return json.dumps(data, ensure_ascii=False, indent=2)
        if ext in {".txt", ".md", ".csv"}:
            with open(filepath, "r", encoding="utf-8") as handle:
                return handle.read()
        if ext in {".xls", ".xlsx"}:
            try:
                import pandas as pd  # type: ignore

                sheets = pd.read_excel(filepath, sheet_name=None)
                parts = []
                for sheet_name, df in sheets.items():
                    parts.append(f"[sheet={sheet_name}]\n{df.to_csv(index=False)}")
                return "\n\n".join(parts)
            except Exception:
                return ""
        return ""

    def _split_and_store_text(self, text: str, source: str) -> bool:
        if not text.strip():
            return False
        if self.vector_db is None:
            return True
        components = self._load_vector_components()
        if components is None:
            return True
        _, document_cls, _, splitter_cls = components
        try:
            splitter = splitter_cls(chunk_size=300, chunk_overlap=20)
            docs = [document_cls(page_content=text, metadata={"source": source, "scope": self.scope_name})]
            splits = splitter.split_documents(docs)
            self.vector_db.add_documents(splits)
            self.vector_db.save_local(str(self.db_path))
            return True
        except Exception as exc:
            console_error(f"向量索引写入失败，已保留原始文档: {exc}")
            return True

    def ingest_knowledge_file(self, filepath: str) -> bool:
        if not os.path.isfile(filepath):
            console_error(f"知识文件不存在: {filepath}")
            return False
        ext = os.path.splitext(filepath)[1].lower()
        if ext not in TEXT_EXTENSIONS:
            return filepath.startswith(str(self.docs_dir))
        try:
            content = self._read_text_content(filepath)
            return self._split_and_store_text(content, source=os.path.basename(filepath))
        except Exception as exc:
            console_error(f"知识文件导入失败 [{filepath}]: {exc}")
            return False

    def save_and_ingest_note(self, text_content: str) -> bool:
        if not text_content or not text_content.strip():
            return False
        filename = f"VoiceNote_{time.strftime('%Y%m%d_%H%M%S')}.txt"
        filepath = self.docs_dir / filename
        filepath.write_text(text_content, encoding="utf-8")
        return self.ingest_knowledge_file(str(filepath))

    def _keyword_score(self, query: str, content: str) -> int:
        query = (query or "").strip().lower()
        haystack = (content or "").lower()
        if not query or not haystack:
            return 0
        score = 0
        score += haystack.count(query) * 12
        tokens = [token for token in query.replace("，", " ").replace(",", " ").split() if len(token) > 1]
        for token in tokens:
            score += haystack.count(token) * 3
        return score

    def _lexical_hits(self, query: str, top_k: int = 3) -> List[Dict[str, str]]:
        hits: List[Dict[str, str]] = []
        for path in sorted(self.docs_dir.rglob("*")):
            if not path.is_file():
                continue
            if path.suffix.lower() not in TEXT_EXTENSIONS:
                continue
            try:
                content = self._read_text_content(str(path))
            except Exception:
                continue
            score = self._keyword_score(query, content)
            if score <= 0:
                continue
            hits.append(
                {
                    "scope": self.scope_name,
                    "source": str(path.relative_to(self.docs_dir)),
                    "content": content[:800],
                    "_score": str(score),
                }
            )
        hits.sort(key=lambda item: int(item.get("_score", "0")), reverse=True)
        return hits[:top_k]

    def retrieve_context(self, query: str, top_k: int = 3) -> str:
        if not query.strip():
            return ""
        if self.vector_db is not None:
            try:
                docs = self.vector_db.similarity_search(query, k=top_k)
                return "\n---\n".join(doc.page_content for doc in docs)
            except Exception:
                pass
        hits = self._lexical_hits(query, top_k=top_k)
        return "\n---\n".join(item["content"] for item in hits)

    def similarity_search(self, query: str, top_k: int = 3) -> List[Dict[str, str]]:
        if not query.strip():
            return []
        if self.vector_db is not None:
            try:
                docs = self.vector_db.similarity_search(query, k=top_k)
                return [
                    {
                        "scope": self.scope_name,
                        "source": str(doc.metadata.get("source", "")),
                        "content": doc.page_content,
                    }
                    for doc in docs
                ]
            except Exception:
                pass
        hits = self._lexical_hits(query, top_k=top_k)
        return [{k: v for k, v in item.items() if not k.startswith("_")} for item in hits]

    def list_docs(self) -> List[str]:
        rows: List[str] = []
        for path in sorted(self.docs_dir.rglob("*")):
            if path.is_file():
                rows.append(str(path.relative_to(self.docs_dir)))
        return rows


class MultiKnowledgeBaseManager:
    def __init__(self) -> None:
        self.base_dir = Path(resource_path("pc/knowledge_base"))
        self.scopes_root = self.base_dir / "scopes"
        self.scopes_root.mkdir(parents=True, exist_ok=True)
        self._scopes: Dict[str, ScopedRAGEngine] = {}

    def normalize_scope(self, scope_name: str) -> str:
        scope = (scope_name or "common").strip()
        return scope or "common"

    def scope_slug(self, scope_name: str) -> str:
        return self.normalize_scope(scope_name).replace("expert.", "expert_").replace(".", "__")

    def scope_title(self, scope_name: str) -> str:
        return scope_title(self.normalize_scope(scope_name))

    def _scope_dirs(self, scope_name: str) -> Tuple[Path, Path, Path]:
        scope = self.normalize_scope(scope_name)
        if scope == "common":
            docs_dir = self.base_dir / "docs"
            db_path = self.base_dir / "faiss_index"
            structured_path = self.base_dir / "structured_kb.sqlite3"
            return docs_dir, db_path, structured_path
        scope_dir = self.scopes_root / self.scope_slug(scope)
        docs_dir = scope_dir / "docs"
        db_path = scope_dir / "faiss_index"
        structured_path = scope_dir / "structured_kb.sqlite3"
        return docs_dir, db_path, structured_path

    def get_scope(self, scope_name: str = "common") -> ScopedRAGEngine:
        scope = self.normalize_scope(scope_name)
        if scope not in self._scopes:
            docs_dir, db_path, _ = self._scope_dirs(scope)
            self._scopes[scope] = ScopedRAGEngine(scope, docs_dir=docs_dir, db_path=db_path, title=self.scope_title(scope))
        return self._scopes[scope]

    def try_get_scope(self, scope_name: str = "common", timeout_s: float = 20.0) -> Tuple[Optional[ScopedRAGEngine], str]:
        scope = self.normalize_scope(scope_name)
        if scope in self._scopes:
            return self._scopes[scope], ""

        holder: Dict[str, object] = {}

        def worker() -> None:
            try:
                holder["engine"] = self.get_scope(scope)
            except Exception as exc:
                holder["error"] = str(exc)

        thread = threading.Thread(target=worker, daemon=True, name=f"KBInit_{scope}")
        thread.start()
        thread.join(timeout_s)
        if thread.is_alive():
            return None, f"作用域 {scope} 初始化超时，已跳过向量索引。"
        if "error" in holder:
            return None, str(holder["error"])
        return holder.get("engine"), ""

    def get_structured_kb(self, scope_name: str = "common") -> StructuredKnowledgeBase:
        scope = self.normalize_scope(scope_name)
        if scope == "common":
            return get_default_structured_kb()
        _, _, structured_path = self._scope_dirs(scope)
        return StructuredKnowledgeBase(str(structured_path))

    def discover_expert_scopes(self) -> List[str]:
        return sorted(known_scopes())

    def list_scopes(self, include_known_experts: bool = True) -> List[Dict[str, object]]:
        scopes = {"common"}
        if self.scopes_root.exists():
            for path in self.scopes_root.iterdir():
                if path.is_dir():
                    slug = path.name
                    if slug.startswith("expert_"):
                        scopes.add("expert." + slug[len("expert_"):].replace("__", "."))
                    else:
                        scopes.add(slug.replace("__", "."))
        if include_known_experts:
            scopes.update(self.discover_expert_scopes())

        rows: List[Dict[str, object]] = []
        for scope in sorted(scopes):
            docs_dir, db_path, structured_path = self._scope_dirs(scope)
            doc_files = sorted(str(p.relative_to(docs_dir)) for p in docs_dir.rglob("*") if p.is_file()) if docs_dir.exists() else []
            rows.append(
                {
                    "scope": scope,
                    "title": self.scope_title(scope),
                    "docs_dir": str(docs_dir),
                    "vector_path": str(db_path),
                    "structured_path": str(structured_path),
                    "doc_count": len(doc_files),
                    "docs": doc_files[:20],
                    "vector_ready": db_path.exists(),
                    "structured_ready": structured_path.exists(),
                }
            )
        return rows

    def import_paths(
        self,
        paths: Iterable[str],
        scope_name: str = "common",
        reset_index: bool = False,
        structured: bool = True,
    ) -> Dict[str, object]:
        scope = self.normalize_scope(scope_name)
        docs_dir, db_path, structured_path = self._scope_dirs(scope)
        docs_dir.mkdir(parents=True, exist_ok=True)
        if reset_index and db_path.exists():
            shutil.rmtree(db_path, ignore_errors=True)
        if reset_index and structured_path.exists():
            try:
                structured_path.unlink()
            except Exception:
                pass

        engine, vector_error = self.try_get_scope(scope, timeout_s=15.0)
        if reset_index and engine is not None:
            engine.reset_index()
        structured_kb = self.get_structured_kb(scope) if structured else None

        imported: List[str] = []
        failed: List[str] = []
        structured_records = 0

        for raw_path in paths:
            path = Path(raw_path)
            if path.is_dir():
                candidates = [
                    item
                    for item in sorted(path.rglob("*"))
                    if item.is_file() and item.suffix.lower() in ALL_IMPORTABLE_EXTENSIONS
                ]
            else:
                candidates = [path]

            for candidate in candidates:
                try:
                    prepared = prepare_knowledge_asset(str(candidate), docs_dir, self.scope_title(scope))
                    vector_ok = engine.ingest_knowledge_file(prepared.index_path) if engine is not None else False
                    added = structured_kb.import_file(prepared.index_path) if structured_kb is not None else 0
                    structured_records += added
                    if vector_ok or added > 0:
                        imported.append(prepared.source_name)
                    else:
                        failed.append(prepared.source_name)
                except Exception:
                    failed.append(candidate.name)

        return {
            "scope": scope,
            "title": self.scope_title(scope),
            "imported": imported,
            "failed": failed,
            "imported_count": len(imported),
            "failed_count": len(failed),
            "structured_records": structured_records,
            "vector_error": vector_error,
        }

    def build_scope_bundle(self, query: str, expert_scope: str = "", top_k: int = 3) -> Dict[str, object]:
        scopes = ["common"]
        scope = self.normalize_scope(expert_scope)
        if scope and scope != "common":
            scopes.append(scope)

        context_parts: List[str] = []
        structured_rows: List[Dict[str, str]] = []
        vector_hits: List[Dict[str, str]] = []
        for name in scopes:
            docs_dir, _, _ = self._scope_dirs(name)
            if docs_dir.exists() and any(docs_dir.rglob("*")):
                try:
                    engine = self.get_scope(name)
                    context = engine.retrieve_context(query, top_k=top_k)
                    if context.strip():
                        context_parts.append(f"[{self.scope_title(name)}]\n{context}")
                    vector_hits.extend(engine.similarity_search(query, top_k=top_k))
                except Exception:
                    pass
            try:
                rows = self.get_structured_kb(name).search(query, limit=top_k)
                for row in rows:
                    structured_rows.append({**row, "scope": name, "scope_title": self.scope_title(name)})
            except Exception:
                pass

        return {
            "query": query,
            "scopes": scopes,
            "context": "\n\n".join(context_parts),
            "structured_rows": structured_rows,
            "vector_hits": vector_hits,
        }


knowledge_manager = MultiKnowledgeBaseManager()


class _LazyCommonScope:
    def __getattr__(self, item):
        return getattr(knowledge_manager.get_scope("common"), item)


rag_engine = _LazyCommonScope()
