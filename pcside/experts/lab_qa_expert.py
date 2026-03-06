import os
import sqlite3
from typing import Dict, List
from pcside.core.base_expert import BaseExpert

class LabQAExpert(BaseExpert):
    """实验室智能问答专家（本地RAG优先，新增历史日志反向检索）。"""

    @property
    def expert_name(self) -> str:
        return "实验室智能问答专家"

    @property
    def expert_version(self) -> str:
        return "2.6.0"

    @staticmethod
    def supported_events() -> List[str]:
        return ["实验室智能问答", "LAB_QA"]

    @staticmethod
    def get_edge_policy() -> Dict:
        # 该专家主要处理文本问答，不要求边缘端图像触发
        return {}

    def match_event(self, event_name: str) -> bool:
        return event_name in self.supported_events()

    @staticmethod
    def _is_history_query(query: str) -> bool:
        """拦截器：判断用户的语音指令是否为查询历史记录或异常日志"""
        keywords = ["刚才", "回放", "记录", "异常", "上一组", "发生什么", "提示了什么", "日志"]
        return any(kw in query for kw in keywords)

    @staticmethod
    def _query_recent_history() -> str:
        """检索本地历史实验记录并转化为口语化播报"""
        db_path = os.path.join(os.path.dirname(__file__), '..', 'knowledge_base', 'structured_kb.db')
        log_path = os.path.join(os.path.dirname(__file__), '..', 'log', 'expert_closed_loop.log')

        # 方案A：优先尝试从 SQLite 数据库提取结构化语义动作
        if os.path.exists(db_path):
            conn = None  # 修复：防止在 connect 时抛错导致 finally 报错
            try:
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='lab_logs'")
                if cursor.fetchone():
                    cursor.execute("SELECT timestamp, risk_level, action_phrases FROM lab_logs ORDER BY id DESC LIMIT 3")
                    rows = cursor.fetchall()
                    if rows:
                        resp = "为您检索到最近的操作记录："
                        for row in rows:
                            t, risk, action = row
                            risk_str = "存在较高风险" if str(risk) in ["high", "2", "3"] else "状态正常"
                            resp += f"在{t}，{action}，系统评估{risk_str}。"
                        return resp + "历史记录播报完毕。"
            except sqlite3.Error as e:  # 修复：缩小异常范围，不再过于宽泛
                print(f"[WARN] SQLite 历史检索异常: {e}")
            finally:
                if conn:  # 修复：确保 conn 成功赋值后再关闭
                    conn.close()

        # 方案B：降级读取现有的文本日志
        if os.path.exists(log_path):
            try:
                with open(log_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    recent_lines = [line.strip() for line in lines if line.strip()][-3:]
                    if recent_lines:
                        logs_str = "。".join(recent_lines)
                        return f"为您检索到最近的系统审计日志：{logs_str[:150]}... 详情请在控制台查看。"
            except IOError as e:  # 修复：缩小异常范围
                print(f"[WARN] 文本日志检索异常: {e}")

        return "为您查阅了底层数据库，当前没有查到最近的操作异常或动作记录。"

    def analyze(self, frame, context) -> str:
        # frame 未使用是 BaseExpert 接口规范要求，可忽略该警告
        question = str(context.get("query") or context.get("question") or "").strip()
        if not question:
            return ""

        # 0) 关键改动：优先拦截历史记录查询指令
        if self._is_history_query(question):
            return self._query_recent_history()

        # 1) 结构化KB优先（规则与目录）
        try:
            from pcside.knowledge_base.structured_kb import get_default_structured_kb
            sk = get_default_structured_kb()
            rows = sk.search(question, limit=3)
            if rows:
                joined = " | ".join([f"{r['name']}:{r['value'][:80]}" for r in rows])
                return f"问答建议：{question}。结构化知识命中：{joined}"
        except Exception as e:
            print(f"[WARN] 结构化知识库检索失败: {e}")

        # 2) 非结构化RAG回退
        try:
            from pcside.knowledge_base.rag_engine import rag_engine
            kb = rag_engine.retrieve_context(question, top_k=3)
            if kb.strip():
                return f"问答建议：{question}。依据知识库：{kb[:180]}"
        except Exception as e:
            print(f"[WARN] 向量知识库检索失败: {e}")

        return f"问答建议：{question}。当前未检索到本地条目，请补充SOP或危化品知识文档后重试。"