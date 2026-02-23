#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rag_test.py - 本地知识库检索增强生成 (RAG) 独立测试引擎
"""
import os
import time
from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.llms import Ollama
from langchain.prompts import PromptTemplate

# 配置路径
KB_DIR = "./knowledge_base"
# 我们推荐使用 Qwen 来做纯文本推理，速度极快且中文逻辑好
# 确保你已经在终端运行过: ollama run qwen2.5:7b (或更高版本)
OLLAMA_MODEL = "qwen2.5:7b"


def build_vector_db():
    print("⏳ [1/3] 正在加载知识库文件...")
    if not os.path.exists(KB_DIR) or not os.listdir(KB_DIR):
        print(f"❌ 错误：请在 {KB_DIR} 文件夹下放入至少一个 .txt 文件！")
        return None

    # 加载目录下所有的 txt 文件
    loader = DirectoryLoader(KB_DIR, glob="**/*.txt", loader_cls=TextLoader, loader_kwargs={'encoding': 'utf-8'})
    docs = loader.load()
    print(f"✅ 成功加载了 {len(docs)} 个文档。")

    print("⏳ [2/3] 正在对文本进行语义切块...")
    # 切块策略：每块 500 字，保留 50 字的重叠防断句
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    chunks = text_splitter.split_documents(docs)
    print(f"✅ 成功将文本切分为 {len(chunks)} 个语义块。")

    print("⏳ [3/3] 正在下载并加载 BGE 向量化模型 (首次运行需联网下载，约1.2GB)...")
    # 使用国产最强开源 embedding 模型
    embeddings = HuggingFaceEmbeddings(model_name="BAAI/bge-large-zh-v1.5")

    print("⏳ 正在构建 FAISS 本地向量数据库...")
    vector_db = FAISS.from_documents(chunks, embeddings)
    print("✅ 向量数据库构建完成！\n")
    return vector_db


def main():
    print("=" * 60)
    print("🧪 微纳流体实验室 - 智能知识问答系统 (RAG 测试版)")
    print("=" * 60)

    vector_db = build_vector_db()
    if vector_db is None: return

    # 初始化 Ollama 文本大模型
    print(f"🔌 正在连接本地 Ollama 模型: {OLLAMA_MODEL}...")
    llm = Ollama(model=OLLAMA_MODEL)

    # 精心设计的专业系统提示词
    prompt_template = PromptTemplate(
        input_variables=["context", "question"],
        template="""你是一个严谨的微纳流体实验室安全与技术专家。
请严格基于以下【参考知识】来回答用户的问题。如果参考知识中没有相关信息，请直接回答“知识库中暂未收录该信息，为了实验室安全，请查阅官方说明书”，绝不允许凭空捏造（幻觉）。

【参考知识】:
{context}

【用户问题】: {question}

请给出专业、清晰、直接的回答："""
    )

    print("\n🎉 系统已就绪！(输入 'q' 或 'quit' 退出)")

    while True:
        question = input("\n👤 请提问: ").strip()
        if question.lower() in ['q', 'quit', 'exit']:
            break
        if not question:
            continue

        start_time = time.time()

        # 1. 向量检索：寻找最相关的 3 个文本块
        docs = vector_db.similarity_search(question, k=3)
        context = "\n".join([doc.page_content for doc in docs])

        # 2. 组装 Prompt
        final_prompt = prompt_template.format(context=context, question=question)

        # 3. 调用大模型生成回答
        print("🤖 专家思考中...")
        response = llm.invoke(final_prompt)

        end_time = time.time()
        print(f"\n💡 【专家解答】 ({round(end_time - start_time, 2)}秒):")
        print(response)


if __name__ == "__main__":
    main()