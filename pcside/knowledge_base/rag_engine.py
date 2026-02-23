# pcside/knowledge_base/rag_engine.py
import os
import time
import logging
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from pcside.core.logger import console_info, console_error

os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["TRANSFORMERS_VERBOSITY"] = "error" # 屏蔽 BertModel UNEXPECTED 提示
logging.getLogger("httpx").setLevel(logging.WARNING) # 屏蔽 HTTP Request 提示
logging.getLogger("sentence_transformers").setLevel(logging.WARNING)
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)

from langchain_community.document_loaders import TextLoader

class RAGEngine:
    def __init__(self):
        # 1. 路径自动规划
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.db_path = os.path.join(self.base_dir, "faiss_index")
        # 存放所有 txt 文本的目录
        self.docs_dir = os.path.join(self.base_dir, "docs")
        os.makedirs(self.docs_dir, exist_ok=True)

        from pcside.core.logger import console_info  # 确保顶部或这里导入了 console_info
        console_info(" 正在加载 RAG 本地语义向量模型，初次启动通常需要几十秒钟，请耐心等待...")

        # 2. 初始化 Embedding 模型 (中文推荐 text2vec)
        try:
            self.embeddings = HuggingFaceEmbeddings(model_name="shibing624/text2vec-base-chinese")
            self.vector_db = None
            self._init_db()
        except Exception as e:
            console_error(f"RAG 引擎初始化失败，请检查模型依赖: {e}")

    def _init_db(self):
        """加载或新建 FAISS 向量数据库"""
        if os.path.exists(self.db_path):
            self.vector_db = FAISS.load_local(self.db_path, self.embeddings, allow_dangerous_deserialization=True)
            console_info(" 已成功加载本地实验室知识库")
        else:
            # 初始化一个空库
            self.vector_db = FAISS.from_texts(["实验室知识库初始化完成\n"], self.embeddings)
            self.vector_db.save_local(self.db_path)
            console_info(" RAG: 尚未发现知识库，已创建全新向量数据库\n")

    def save_and_ingest_note(self, text_content: str) -> bool:
        """
        核心功能：将语音识别的文本存为 TXT，并立即录入大模型记忆
        """
        if not text_content or not text_content.strip():
            return False

        # 1. 生成带时间戳的 txt 文件
        timestamp = time.strftime('%Y%m%d_%H%M%S')
        filename = f"VoiceNote_{timestamp}.txt"
        filepath = os.path.join(self.docs_dir, filename)

        try:
            # 2. 保存为物理文件，方便人类后续直接查阅
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(text_content)

            # 3. 立即向量化并存入 FAISS
            loader = TextLoader(filepath, encoding='utf-8')
            docs = loader.load()
            # 语音片段通常较短，适当缩小 chunk
            splitter = RecursiveCharacterTextSplitter(chunk_size=300, chunk_overlap=20)
            splits = splitter.split_documents(docs)

            self.vector_db.add_documents(splits)
            self.vector_db.save_local(self.db_path)

            console_info(f"📝 语音记忆已存档至 [{filename}] 并完成向量学习！")
            return True
        except Exception as e:
            console_error(f"语音记忆入库失败: {e}")
            return False

    def retrieve_context(self, query: str, top_k: int = 3) -> str:
        """检索相关知识"""
        if not self.vector_db: return ""
        docs = self.vector_db.similarity_search(query, k=top_k)
        return "\n---\n".join([doc.page_content for doc in docs])


# 采用单例模式导出，确保全局只有一个数据库实例
rag_engine = RAGEngine()