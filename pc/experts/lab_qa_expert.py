from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Dict, List

from pc.app_identity import resource_path
from pc.core.base_expert import BaseExpert


class LabQAExpert(BaseExpert):
    """实验室智能问答专家。"""

    @property
    def expert_name(self) -> str:
        return "实验室智能问答专家"

    @property
    def expert_version(self) -> str:
        return "2.7.0"

    @staticmethod
    def supported_events() -> List[str]:
        return ["实验室智能问答", "LAB_QA"]

    @staticmethod
    def get_edge_policy() -> Dict:
        return {}

    def match_event(self, event_name: str) -> bool:
        return event_name in self.supported_events()

    @staticmethod
    def _is_history_query(query: str) -> bool:
        keywords = ["刚才", "回放", "记录", "异常", "上一组", "发生什么", "提示了什么", "日志"]
        return any(keyword in query for keyword in keywords)

    @staticmethod
    def _query_recent_history() -> str:
        db_path = Path(resource_path("pc/knowledge_base/structured_kb.sqlite3"))
        log_path = Path(resource_path("pc/log/expert_closed_loop.log"))

        if db_path.exists():
            conn = None
            try:
                conn = sqlite3.connect(str(db_path))
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='lab_logs'")
                if cursor.fetchone():
                    cursor.execute("SELECT timestamp, risk_level, action_phrases FROM lab_logs ORDER BY id DESC LIMIT 3")
                    rows = cursor.fetchall()
                    if rows:
                        lines = ["为您检索到最近的操作记录："]
                        for timestamp, risk_level, action_phrases in rows:
                            risk_text = "存在较高风险" if str(risk_level) in {"high", "2", "3"} else "状态正常"
                            lines.append(f"在 {timestamp}，{action_phrases}，系统评估为 {risk_text}。")
                        lines.append("历史记录播报完毕。")
                        return "".join(lines)
            except sqlite3.Error as exc:
                print(f"[WARN] SQLite 历史检索异常: {exc}")
            finally:
                if conn:
                    conn.close()

        if log_path.exists():
            try:
                with log_path.open("r", encoding="utf-8") as handle:
                    lines = [line.strip() for line in handle.readlines() if line.strip()]
                if lines:
                    logs_str = "。".join(lines[-3:])
                    return f"为您检索到最近的系统审计日志：{logs_str[:150]}... 详情请在控制台查看。"
            except OSError as exc:
                print(f"[WARN] 文本日志检索异常: {exc}")

        return "为您查阅了底层数据库，当前没有查到最近的操作异常或动作记录。"

    def analyze(self, frame, context) -> str:
        question = str(context.get("query") or context.get("question") or "").strip()
        if not question:
            return ""

        if self._is_history_query(question):
            return self._query_recent_history()

        structured_rows = context.get("knowledge_structured_rows") or []
        if structured_rows:
            joined = " | ".join(
                f"[{row.get('scope_title', row.get('scope', '知识库'))}] {row.get('name', '')}:{str(row.get('value', ''))[:80]}"
                for row in structured_rows[:3]
            )
            return f"问答建议：{question}。结构化知识命中：{joined}"

        kb_context = str(context.get("knowledge_context") or "").strip()
        if kb_context:
            return f"问答建议：{question}。依据知识库：{kb_context[:180]}"

        try:
            from pc.knowledge_base.rag_engine import knowledge_manager

            bundle = knowledge_manager.build_scope_bundle(question, self.knowledge_scope, top_k=3)
            if bundle["structured_rows"]:
                row = bundle["structured_rows"][0]
                return f"问答建议：{question}。结构化知识命中：{row['name']}:{str(row['value'])[:120]}"
            if str(bundle["context"]).strip():
                return f"问答建议：{question}。依据知识库：{str(bundle['context'])[:180]}"
        except Exception as exc:
            print(f"[WARN] 多知识库检索失败: {exc}")

        return f"问答建议：{question}。当前未检索到本地条目，请补充 SOP 或危化品知识文档后重试。"
