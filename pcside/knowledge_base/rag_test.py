# pcside/knowledge_base/rag_test.py
import os
import sys

# 把项目根目录加进来防止找不到包
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
if project_root not in sys.path:
    sys.path.append(project_root)

from pcside.knowledge_base.rag_engine import rag_engine


def manual_ingest():
    # 假设你的 txt 放在了 knowledge_base/docs/content.txt 下
    txt_path = os.path.join(rag_engine.base_dir, "docs", "content.txt")

    if not os.path.exists(txt_path):
        print(f"❌ 找不到文件: {txt_path}")
        return

    print(f"正在读取并向量化: {txt_path} ...")

    with open(txt_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 调用引擎的录入接口
    success = rag_engine.save_and_ingest_note(content)

    if success:
        print("✅ 手动灌库成功！你可以去问小爱同学了。")

        # 顺便测试一下检索效果
        print("\n=== 检索测试 ===")
        # 你可以把 "实验室" 替换成你 content.txt 里的真实关键词
        res = rag_engine.retrieve_context("你的关键词")
        print(res)


if __name__ == "__main__":
    manual_ingest()