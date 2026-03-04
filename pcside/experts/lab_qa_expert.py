from typing import Dict, List

from pcside.core.base_expert import BaseExpert


class LabQAExpert(BaseExpert):
    """实验室智能问答专家（本地RAG优先）。"""

    @property
    def expert_name(self) -> str:
        return "实验室智能问答专家"

    @property
    def expert_version(self) -> str:
        return "2.5"

    def supported_events(self) -> List[str]:
        return ["实验室智能问答", "LAB_QA"]

    def get_edge_policy(self) -> Dict:
        # 该专家主要处理文本问答，不要求边缘端图像触发
        return {}

    def match_event(self, event_name: str) -> bool:
        return event_name in self.supported_events()

    def analyze(self, frame, context) -> str:
        question = str(context.get("query") or context.get("question") or "").strip()
        if not question:
            return ""

        # 1) 结构化KB优先（规则与目录）
        try:
            from pcside.knowledge_base.structured_kb import get_default_structured_kb

            sk = get_default_structured_kb()
            rows = sk.search(question, limit=3)
            if rows:
                joined = " | ".join([f"{r['name']}:{r['value'][:80]}" for r in rows])
                return f"问答建议：{question}。结构化知识命中：{joined}"
        except Exception:
            pass

        # 2) 非结构化RAG回退
        try:
            from pcside.knowledge_base.rag_engine import rag_engine

            kb = rag_engine.retrieve_context(question, top_k=3)
            if kb.strip():
                return f"问答建议：{question}。依据知识库：{kb[:180]}"
        except Exception:
            pass

        return f"问答建议：{question}。当前未检索到本地条目，请补充SOP/危化品知识文档后重试。"