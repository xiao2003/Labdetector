#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GUI 级验证：Ollama qwen3.5:4b 就绪/拉取与外部知识导入后参与推理。"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List

import tkinter.messagebox as messagebox

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pc.core.ai_backend import ask_assistant_with_rag, list_ollama_models
from pc.core.config import get_config, set_config
from pc.desktop_app import DesktopApp
from pc.knowledge_base.rag_engine import knowledge_manager

REPORT_PATH = ROOT / "tmp" / "gui_ollama_knowledge_flow_report.json"
ASSET_DIR = ROOT / "tmp" / "gui_ollama_knowledge_flow_assets"


class GuiOllamaKnowledgeTester:
    """通过桌面 GUI 驱动最小闭环，不引入额外业务逻辑。"""

    def __init__(self) -> None:
        self.start_ts = time.time()
        self.report: Dict[str, Any] = {
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "steps": [],
            "dialogs": [],
        }
        self.app = DesktopApp()
        self.asset_file = ASSET_DIR / "external_hf_guideline.txt"
        self.original_inference_timeout = str(get_config("inference.timeout", "20"))

    def _patch_dialogs(self) -> None:
        def _log(kind: str, title: str, message: str) -> None:
            self.report["dialogs"].append(
                {
                    "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "kind": kind,
                    "title": title,
                    "message": message,
                }
            )

        messagebox.askyesno = lambda title, message, **kwargs: (_log("askyesno", title, message), False)[1]  # type: ignore[assignment]
        messagebox.showinfo = lambda title, message, **kwargs: (_log("showinfo", title, message), True)[1]  # type: ignore[assignment]
        messagebox.showwarning = lambda title, message, **kwargs: (_log("showwarning", title, message), True)[1]  # type: ignore[assignment]
        messagebox.showerror = lambda title, message, **kwargs: (_log("showerror", title, message), True)[1]  # type: ignore[assignment]

    def _record_step(self, step: str, status: str, **extra: Any) -> None:
        row = {
            "step": step,
            "status": status,
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        row.update(extra)
        self.report["steps"].append(row)

    def _wait_until(self, predicate: Callable[[], bool], timeout: float, message: str) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            self.app.root.update_idletasks()
            self.app.root.update()
            if predicate():
                return
            time.sleep(0.1)
        raise TimeoutError(message)

    def _set_backend(self, backend: str) -> None:
        label = getattr(
            self.app,
            "backend_reverse",
            {},
        ).get(
            backend,
            next((key for key, value in self.app.backend_map.items() if value == backend), self.app.backend_combo.get()),
        )
        self.app.backend_var.set(backend)
        values = list(self.app.backend_combo.cget("values") or [])
        if label in values:
            self.app.backend_combo.current(values.index(label))
        else:
            self.app.backend_combo.set(label)
        self.app.backend_combo.event_generate("<<ComboboxSelected>>")
        self.app._update_model_choices()
        self.app.root.update_idletasks()
        self.app.root.update()

    def _set_mode(self, mode: str) -> None:
        label = getattr(
            self.app,
            "mode_reverse",
            {},
        ).get(mode, next((key for key, value in self.app.mode_map.items() if value == mode), self.app.mode_combo.get()))
        self.app.mode_var.set(mode)
        values = list(self.app.mode_combo.cget("values") or [])
        if label in values:
            self.app.mode_combo.current(values.index(label))
        else:
            self.app.mode_combo.set(label)
        self.app.mode_combo.event_generate("<<ComboboxSelected>>")
        self.app.root.update_idletasks()
        self.app.root.update()
        self.app._sync_field_visibility()

    def _write_external_knowledge(self) -> None:
        ASSET_DIR.mkdir(parents=True, exist_ok=True)
        self.asset_file.write_text(
            (
                "外部危化品规范测试库\n"
                "1. 氢氟酸（HF）接触皮肤后的第一步处置：立即使用大量流动清水持续冲洗至少15分钟。\n"
                "2. 冲洗后必须立即报告，并尽快按实验室急救流程处理。\n"
                "3. 本条用于 GUI 外部知识导入与模型推理联合验证。\n"
            ),
            encoding="utf-8",
        )

    def _run(self) -> None:
        self._patch_dialogs()

        self._wait_until(
            lambda: self.app.runtime is not None and bool(self.app.current_state),
            timeout=45.0,
            message="主界面启动超时",
        )
        self._record_step("wait_ready", "pass")
        set_config("inference.timeout", "120")

        before_models = list_ollama_models()
        had_model_before = "qwen3.5:4b" in before_models
        self._record_step("before_ollama_catalog", "pass", models=before_models, had_qwen35_4b=had_model_before)

        self._set_backend("ollama")
        self._set_mode("websocket")
        self.app.model_combo.set("qwen3.5:4b")
        self.app.expected_entry.delete(0, "end")
        self.app.expected_entry.insert(0, "1")
        self.app._start_session()
        self._wait_until(
            lambda: str((self.app.current_state.get("session") or {}).get("phase") or "").lower() == "running",
            timeout=2400.0,
            message="Ollama qwen3.5:4b 未能在 GUI 中启动成功",
        )

        after_models = list_ollama_models()
        has_model_after = "qwen3.5:4b" in after_models
        if not has_model_after:
            raise RuntimeError("GUI 启动后 Ollama 模型列表中仍未出现 qwen3.5:4b")
        self._record_step(
            "ollama_qwen35_4b_ready",
            "pass",
            pulled_during_test=(not had_model_before and has_model_after),
            models=after_models,
        )

        self.app._show_knowledge_base_window()
        self._wait_until(
            lambda: self.app.kb_window is not None and self.app.kb_window.winfo_exists(),
            timeout=10.0,
            message="知识库窗口未打开",
        )
        self._write_external_knowledge()
        summary = self.app.runtime.import_knowledge_paths([str(self.asset_file)], scope_name="common")
        self.app.kb_status_var.set(
            f"导入完成: 作用域 {summary['scope']}，成功 {summary['imported_count']} 项，失败 {summary['failed_count']} 项"
        )
        self.app._refresh_knowledge_bases()
        self._record_step(
            "gui_import_external_knowledge",
            "pass",
            asset=str(self.asset_file),
            kb_status=self.app.kb_status_var.get(),
            imported_count=summary.get("imported_count"),
            failed_count=summary.get("failed_count"),
        )

        self.app._stop_session()
        self._wait_until(
            lambda: str((self.app.current_state.get("session") or {}).get("phase") or "").lower() in {"idle", ""},
            timeout=30.0,
            message="知识导入后监控未能正常停止",
        )
        self._record_step("stop_session_before_inference", "pass")

        question = "根据外部危化品规范，HF 接触皮肤后的第一步处置是什么？"
        bundle = knowledge_manager.build_scope_bundle(question, "common", top_k=3)
        answer = str(ask_assistant_with_rag(None, question, str(bundle.get("context") or ""), "qwen3.5:4b") or "").strip()
        ok = ("流动清水" in answer or "持续冲洗" in answer or "至少15分钟" in answer)
        if not ok:
            raise RuntimeError(f"模型回答未体现导入知识: {answer}")
        self._record_step(
            "knowledge_inference",
            "pass",
            question=question,
            answer=answer,
            knowledge_scopes=bundle.get("scopes", []),
        )

        self._record_step("finish", "pass")

    def run(self) -> int:
        try:
            self._run()
            self.report["status"] = "pass"
            return 0
        except Exception as exc:
            self.report["status"] = "fail"
            self.report["error"] = str(exc)
            self._record_step("failure", "fail", detail=str(exc))
            return 1
        finally:
            try:
                set_config("inference.timeout", self.original_inference_timeout)
            except Exception:
                pass
            self.report["duration_ms"] = int((time.time() - self.start_ts) * 1000)
            REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
            REPORT_PATH.write_text(json.dumps(self.report, ensure_ascii=False, indent=2), encoding="utf-8-sig")
            try:
                self.app.root.after(100, self.app._on_close)
                self.app.root.update_idletasks()
                self.app.root.update()
            except Exception:
                pass


def main() -> int:
    return GuiOllamaKnowledgeTester().run()


if __name__ == "__main__":
    raise SystemExit(main())
