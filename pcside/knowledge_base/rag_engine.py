# pcside/knowledge_base/rag_engine.py
import json
import logging
import os
import time
from typing import List, Tuple

from langchain_community.document_loaders import TextLoader
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from pcside.core.logger import console_info, console_error

os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["TRANSFORMERS_VERBOSITY"] = "error"
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("sentence_transformers").setLevel(logging.WARNING)
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)


class RAGEngine:
    SUPPORTED_EXTENSIONS = {".txt", ".md", ".csv", ".json", ".xls", ".xlsx"}

    def __init__(self):
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.db_path = os.path.join(self.base_dir, "faiss_index")
        self.docs_dir = os.path.join(self.base_dir, "docs")
        os.makedirs(self.docs_dir, exist_ok=True)

        console_info("正在加载 RAG 本地语义向量模型，首次启动通常需要几十秒钟，请耐心等待...")

        try:
            self.embeddings = HuggingFaceEmbeddings(model_name="shibing624/text2vec-base-chinese")
            self.vector_db = None
            self._init_db()
        except Exception as e:
            console_error(f"RAG 引擎初始化失败，请检查模型依赖: {e}")

    def _init_db(self):
        if os.path.exists(self.db_path):
            self.vector_db = FAISS.load_local(self.db_path, self.embeddings, allow_dangerous_deserialization=True)
            console_info("已成功加载本地实验室知识库")
        else:
            self.vector_db = FAISS.from_texts(["实验室知识库初始化完成\n"], self.embeddings)
            self.vector_db.save_local(self.db_path)
            console_info("未发现知识库，已创建全新向量数据库\n")

    def _split_and_store_text(self, text: str, source: str) -> bool:
        if not text.strip() or not self.vector_db:
            return False

        from langchain_core.documents import Document

        splitter = RecursiveCharacterTextSplitter(chunk_size=300, chunk_overlap=20)
        docs = [Document(page_content=text, metadata={"source": source})]
        splits = splitter.split_documents(docs)

        self.vector_db.add_documents(splits)
        self.vector_db.save_local(self.db_path)
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
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            return True, json.dumps(data, ensure_ascii=False, indent=2)
        if ext in {".txt", ".md"}:
            with open(filepath, "r", encoding="utf-8") as f:
                return True, f.read()
        return False, ""

    def ingest_knowledge_file(self, filepath: str) -> bool:
        """导入单个知识文件，支持 txt/md/csv/json/xlsx。"""
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
            success = self._split_and_store_text(content, source=os.path.basename(filepath))
            if success:
                console_info(f"知识库导入成功: {os.path.basename(filepath)}")
            return success
        except Exception as e:
            console_error(f"知识文件导入失败 [{filepath}]: {e}")
            return False

    def ingest_knowledge_directory(self, directory: str) -> List[str]:
        """批量导入知识目录中的所有支持格式文件。"""
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

        timestamp = time.strftime('%Y%m%d_%H%M%S')
        filename = f"VoiceNote_{timestamp}.txt"
        filepath = os.path.join(self.docs_dir, filename)

        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(text_content)

            loader = TextLoader(filepath, encoding='utf-8')
            docs = loader.load()
            splitter = RecursiveCharacterTextSplitter(chunk_size=300, chunk_overlap=20)
            splits = splitter.split_documents(docs)

            self.vector_db.add_documents(splits)
            self.vector_db.save_local(self.db_path)

            console_info(f"语音记忆已存档至 [{filename}] 并完成向量学习！")
            return True
        except Exception as e:
            console_error(f"语音记忆入库失败: {e}")
            return False

    def retrieve_context(self, query: str, top_k: int = 3) -> str:
        if not self.vector_db:
            return ""
        docs = self.vector_db.similarity_search(query, k=top_k)
        return "\n---\n".join([doc.page_content for doc in docs])


rag_engine = RAGEngine()