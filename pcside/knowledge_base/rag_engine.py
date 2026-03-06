# pcside/knowledge_base/rag_engine.py
from __future__ import annotations

import json
import logging
import os
import shutil
import threading
import time
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from pcside.core.logger import console_error, console_info
from pcside.knowledge_base.structured_kb import StructuredKnowledgeBase, get_default_structured_kb

os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["TRANSFORMERS_VERBOSITY"] = "error"
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("sentence_transformers").setLevel(logging.WARNING)
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)


class ScopedRAGEngine:
    SUPPORTED_EXTENSIONS = {".txt", ".md", ".csv", ".json", ".xls", ".xlsx"}
    _shared_embeddings = None
    _embeddings_failed = False

    def __init__(self, scope_name: str, docs_dir: Path, db_path: Path, title: str = ""):
        self.scope_name = scope_name
        self.title = title or scope_name
        self.docs_dir = docs_dir
        self.db_path = db_path
        self.base_dir = str(docs_dir.parent)
        self.docs_dir.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.vector_db = None
        self._init_db()

    @classmethod
    def _get_embeddings(cls):
        if cls._shared_embeddings is not None:
            return cls._shared_embeddings
        if cls._embeddings_failed:
            raise RuntimeError("embedding model unavailable")
        console_info("正在加载 RAG 本地语义向量模型，首次启动通常需要几十秒，请耐心等待...")
        try:
            cls._shared_embeddings = HuggingFaceEmbeddings(model_name="shibing624/text2vec-base-chinese")
            return cls._shared_embeddings
        except Exception as exc:
            cls._embeddings_failed = True
            console_error(f"RAG 引擎初始化失败，请检查模型依赖: {exc}")
            raise

    def _init_db(self):
        try:
            embeddings = self._get_embeddings()
        except Exception:
            self.vector_db = None
            return

        if self.db_path.exists():
            self.vector_db = FAISS.load_local(str(self.db_path), embeddings, allow_dangerous_deserialization=True)
            if self.scope_name == "common":
                console_info("已成功加载本地实验室知识库")
            return

        self.vector_db = FAISS.from_texts(["实验室知识库初始化完成\n"], embeddings)
        self.vector_db.save_local(str(self.db_path))
        if self.scope_name == "common":
            console_info("未发现知识库，已创建全新向量数据库\n")

    def reset_index(self) -> None:
        if self.db_path.exists():
            shutil.rmtree(self.db_path, ignore_errors=True)
        self._init_db()

    def _split_and_store_text(self, text: str, source: str) -> bool:
        if not text.strip() or not self.vector_db:
            return False
        splitter = RecursiveCharacterTextSplitter(chunk_size=300, chunk_overlap=20)
        docs = [Document(page_content=text, metadata={"source": source, "scope": self.scope_name})]
        splits = splitter.split_documents(docs)
        self.vector_db.add_documents(splits)
        self.vector_db.save_local(str(self.db_path))
        return True

    def _normalize_structured_file(self, filepath: str) -> Tuple[bool, str]:
        ext = os.path.splitext(filepath)[1].lower()
        if ext == ".csv":
            import pandas as pd

            df = pd.read_csv(filepath)
            return True, df.to_csv(index=False)
        if ext in {".xls", ".xlsx"}:
            import pandas as pd

            sheets = pd.read_excel(filepath, sheet_name=None)
            merged = []
            for sheet_name, df in sheets.items():
                merged.append(f"[sheet={sheet_name}]\n{df.to_csv(index=False)}")
            return True, "\n\n".join(merged)
        if ext == ".json":
            with open(filepath, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            return True, json.dumps(data, ensure_ascii=False, indent=2)
        if ext in {".txt", ".md"}:
            with open(filepath, "r", encoding="utf-8") as handle:
                return True, handle.read()
        return False, ""

    def _archive_source_file(self, filepath: str) -> str:
        source = Path(filepath)
        target = self.docs_dir / source.name
        if source.resolve() == target.resolve():
            return str(target)
        if target.exists():
            stem = target.stem
            suffix = target.suffix
            target = self.docs_dir / f"{stem}_{int(time.time())}{suffix}"
        shutil.copy2(str(source), str(target))
        return str(target)

    def ingest_knowledge_file(self, filepath: str) -> bool:
        if not os.path.isfile(filepath):
            console_error(f"知识文件不存在: {filepath}")
            return False

        ext = os.path.splitext(filepath)[1].lower()
        if ext not in self.SUPPORTED_EXTENSIONS:
            console_error(f"暂不支持的知识文件格式: {ext}")
            return False

        try:
            ok, content = self._normalize_structured_file(filepath)
            if not ok:
                return False
            archived_path = self._archive_source_file(filepath)
            success = self._split_and_store_text(content, source=os.path.basename(archived_path))
            if success:
                console_info(f"知识库导入成功: {os.path.basename(archived_path)}")
            return success
        except Exception as exc:
            console_error(f"知识文件导入失败 [{filepath}]: {exc}")
            return False

    def ingest_knowledge_directory(self, directory: str) -> List[str]:
        if not os.path.isdir(directory):
            console_error(f"知识目录不存在: {directory}")
            return []

        imported = []
        for name in sorted(os.listdir(directory)):
            full_path = os.path.join(directory, name)
            if os.path.isfile(full_path) and os.path.splitext(name)[1].lower() in self.SUPPORTED_EXTENSIONS:
                if self.ingest_knowledge_file(full_path):
                    imported.append(name)
        return imported

    def save_and_ingest_note(self, text_content: str) -> bool:
        if not text_content or not text_content.strip():
            return False

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"VoiceNote_{timestamp}.txt"
        filepath = self.docs_dir / filename

        try:
            filepath.write_text(text_content, encoding="utf-8")
            success = self._split_and_store_text(text_content, source=filename)
            if success:
                console_info(f"语音记忆已存档至 [{filename}] 并完成向量学习！")
            return success
        except Exception as exc:
            console_error(f"语音记忆入库失败: {exc}")
            return False

    def retrieve_context(self, query: str, top_k: int = 3) -> str:
        if not self.vector_db or not query.strip():
            return ""
        docs = self.vector_db.similarity_search(query, k=top_k)
        return "\n---\n".join(doc.page_content for doc in docs)

    def similarity_search(self, query: str, top_k: int = 3) -> List[Dict[str, str]]:
        if not self.vector_db or not query.strip():
            return []
        docs = self.vector_db.similarity_search(query, k=top_k)
        hits: List[Dict[str, str]] = []
        for doc in docs:
            hits.append(
                {
                    "scope": self.scope_name,
                    "source": str(doc.metadata.get("source", "")),
                    "content": doc.page_content,
                }
            )
        return hits

    def list_docs(self) -> List[str]:
        return sorted(path.name for path in self.docs_dir.iterdir() if path.is_file())


class MultiKnowledgeBaseManager:
    def __init__(self):
        self.base_dir = Path(__file__).resolve().parent
        self.scopes_root = self.base_dir / "scopes"
        self.scopes_root.mkdir(parents=True, exist_ok=True)
        self._scopes: Dict[str, ScopedRAGEngine] = {}

    def normalize_scope(self, scope_name: str) -> str:
        scope = (scope_name or "common").strip()
        return scope or "common"

    def scope_slug(self, scope_name: str) -> str:
        return self.normalize_scope(scope_name).replace("expert.", "expert_").replace(".", "__")

    def scope_title(self, scope_name: str) -> str:
        scope = self.normalize_scope(scope_name)
        if scope == "common":
            return "公共底座知识库"
        if scope.startswith("expert."):
            return f"专家知识库 / {scope[len('expert.'):] }"
        return scope

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
        if scope in self._scopes:
            return self._scopes[scope]
        docs_dir, db_path, _ = self._scope_dirs(scope)
        engine = ScopedRAGEngine(scope, docs_dir=docs_dir, db_path=db_path, title=self.scope_title(scope))
        self._scopes[scope] = engine
        return engine

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
            return None, f"作用域 {scope} 的向量模型初始化超时，已跳过向量索引导入"
        if "error" in holder:
            return None, str(holder["error"])
        return holder.get("engine"), ""

    def get_structured_kb(self, scope_name: str = "common") -> StructuredKnowledgeBase:
        scope = self.normalize_scope(scope_name)
        if scope == "common":
            return get_default_structured_kb()
        _, _, structured_path = self._scope_dirs(scope)
        return StructuredKnowledgeBase(str(structured_path))

    def list_scopes(self, include_known_experts: bool = True) -> List[Dict[str, object]]:
        scopes = {"common"}
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
            doc_files = sorted(p.name for p in docs_dir.iterdir() if p.is_file()) if docs_dir.exists() else []
            rows.append(
                {
                    "scope": scope,
                    "title": self.scope_title(scope),
                    "docs_dir": str(docs_dir),
                    "vector_path": str(db_path),
                    "structured_path": str(structured_path),
                    "doc_count": len(doc_files),
                    "docs": doc_files[:12],
                    "vector_ready": db_path.exists(),
                    "structured_ready": structured_path.exists(),
                }
            )
        return rows

    def discover_expert_scopes(self) -> List[str]:
        experts_dir = self.base_dir.parent / "experts"
        scopes = []
        if not experts_dir.exists():
            return scopes
        for file_path in experts_dir.rglob("*.py"):
            if file_path.name.startswith("__"):
                continue
            rel = file_path.relative_to(experts_dir).with_suffix("")
            scopes.append(f"expert.{str(rel).replace(os.sep, '.')}" )
        return sorted(set(scopes))

    def import_paths(
        self,
        paths: Iterable[str],
        scope_name: str = "common",
        reset_index: bool = False,
        structured: bool = True,
    ) -> Dict[str, object]:
        scope = self.normalize_scope(scope_name)
        _, db_path, structured_path = self._scope_dirs(scope)
        if reset_index and db_path.exists():
            shutil.rmtree(db_path, ignore_errors=True)
        if reset_index and scope != "common" and structured_path.exists():
            structured_path.unlink()

        engine, vector_error = self.try_get_scope(scope, timeout_s=20.0)
        if reset_index and engine is not None:
            engine.reset_index()

        sk = self.get_structured_kb(scope) if structured else None
        imported: List[str] = []
        failed: List[str] = []
        structured_records = 0
        for path in paths:
            if os.path.isdir(path):
                candidates = [
                    os.path.join(path, name)
                    for name in sorted(os.listdir(path))
                    if os.path.isfile(os.path.join(path, name))
                    and os.path.splitext(name)[1].lower() in ScopedRAGEngine.SUPPORTED_EXTENSIONS
                ]
            else:
                candidates = [path]

            for candidate in candidates:
                vector_ok = engine.ingest_knowledge_file(candidate) if engine is not None else False
                structured_added = 0
                if sk is not None:
                    try:
                        structured_added = sk.import_file(candidate)
                    except Exception:
                        structured_added = 0
                if vector_ok or structured_added > 0:
                    if not vector_ok and structured_added > 0:
                        docs_dir, _, _ = self._scope_dirs(scope)
                        docs_dir.mkdir(parents=True, exist_ok=True)
                        source = Path(candidate)
                        target = docs_dir / source.name
                        if source.resolve() != target.resolve():
                            if target.exists():
                                target = docs_dir / f"{target.stem}_{int(time.time())}{target.suffix}"
                            shutil.copy2(str(source), str(target))
                    imported.append(os.path.basename(candidate))
                    structured_records += structured_added
                else:
                    failed.append(os.path.basename(candidate))

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
            docs_dir, db_path, _ = self._scope_dirs(name)
            if db_path.exists() or (docs_dir.exists() and any(docs_dir.iterdir())):
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
                continue

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
