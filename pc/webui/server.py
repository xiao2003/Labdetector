#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""HTTP server for the LabDetector web console."""

from __future__ import annotations

import json
import mimetypes
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict
from urllib.parse import unquote, urlparse

from pc.app_identity import resource_path

from .runtime import LabDetectorRuntime


class DashboardServer(ThreadingHTTPServer):
    def __init__(self, host: str, port: int, runtime: LabDetectorRuntime) -> None:
        self.runtime = runtime
        self.static_root = Path(resource_path("pc/webui/static"))
        super().__init__((host, port), DashboardHandler)


class DashboardHandler(BaseHTTPRequestHandler):
    server_version = "LabDetectorDashboard/1.0"

    @property
    def runtime(self) -> LabDetectorRuntime:
        return self.server.runtime  # type: ignore[attr-defined]

    @property
    def static_root(self) -> Path:
        return self.server.static_root  # type: ignore[attr-defined]

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/bootstrap":
            self._send_json(self.runtime.bootstrap())
            return
        if parsed.path == "/api/experts":
            self._send_json({"ok": True, "experts": self.runtime.get_expert_catalog()})
            return
        if parsed.path == "/api/knowledge-bases":
            self._send_json({"ok": True, "knowledge_bases": self.runtime.get_knowledge_base_catalog()})
            return
        if parsed.path == "/api/cloud-backends":
            self._send_json({"ok": True, "cloud_backends": self.runtime.get_cloud_backend_catalog()})
            return
        if parsed.path == "/api/training":
            self._send_json({"ok": True, "training": self.runtime.get_training_overview()})
            return
        if parsed.path == "/api/archives":
            self._send_json({"ok": True, "archives": self.runtime.get_archive_catalog()})
            return
        if parsed.path.startswith("/api/archives/"):
            session_id = unquote(parsed.path.split("/api/archives/", 1)[1])
            try:
                self._send_json({"ok": True, "detail": self.runtime.get_archive_detail(session_id)})
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, status=404)
            return
        if parsed.path == "/api/state":
            self._send_json(self.runtime.get_state())
            return
        if parsed.path.startswith("/api/frame/"):
            stream_id = unquote(parsed.path.split("/api/frame/", 1)[1])
            self._send_frame(stream_id)
            return
        self._serve_static(parsed.path)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        body = self._read_json_body()
        if parsed.path == "/api/self-check":
            checks = self.runtime.run_self_check()
            self._send_json({"ok": True, "checks": checks, "state": self.runtime.get_state()})
            return
        if parsed.path == "/api/models/refresh":
            catalog = self.runtime.refresh_model_catalog()
            self._send_json({"ok": True, "models": catalog, "state": self.runtime.get_state()})
            return
        if parsed.path == "/api/session/start":
            try:
                state = self.runtime.start_session(body)
                self._send_json({"ok": True, "state": state})
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc), "state": self.runtime.get_state()}, status=400)
            return
        if parsed.path == "/api/session/stop":
            state = self.runtime.stop_session()
            self._send_json({"ok": True, "state": state})
            return
        if parsed.path == "/api/experts/import":
            try:
                summary = self.runtime.import_expert_assets(str(body.get("expert_code") or ""), self._paths_field(body.get("paths")))
                self._send_json({
                    "ok": True,
                    "summary": summary,
                    "experts": self.runtime.get_expert_catalog(),
                    "state": self.runtime.get_state(),
                })
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, status=400)
            return
        if parsed.path == "/api/knowledge/import":
            try:
                summary = self.runtime.import_knowledge_paths(
                    self._paths_field(body.get("paths")),
                    scope_name=str(body.get("scope_name") or "common"),
                    reset_index=bool(body.get("reset_index", False)),
                    structured=bool(body.get("structured", True)),
                )
                self._send_json({
                    "ok": True,
                    "summary": summary,
                    "knowledge_bases": self.runtime.get_knowledge_base_catalog(),
                    "state": self.runtime.get_state(),
                })
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, status=400)
            return
        if parsed.path == "/api/cloud-backends/save":
            try:
                summary = self.runtime.save_cloud_backend_config(
                    str(body.get("backend") or ""),
                    api_key=str(body.get("api_key") or ""),
                    base_url=str(body.get("base_url") or ""),
                    model=str(body.get("model") or ""),
                )
                self._send_json({
                    "ok": True,
                    "summary": summary,
                    "cloud_backends": self.runtime.get_cloud_backend_catalog(),
                    "state": self.runtime.get_state(),
                })
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, status=400)
            return
        if parsed.path == "/api/training/workspace":
            try:
                summary = self.runtime.build_training_workspace(str(body.get("workspace_name") or ""))
                self._send_json({"ok": True, "summary": summary, "training": self.runtime.get_training_overview()})
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, status=400)
            return
        if parsed.path == "/api/training/import-llm":
            try:
                summary = self.runtime.import_llm_training_data(self._paths_field(body.get("paths")))
                self._send_json({"ok": True, "summary": summary, "training": self.runtime.get_training_overview()})
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, status=400)
            return
        if parsed.path == "/api/training/import-pi":
            try:
                summary = self.runtime.import_pi_training_data(self._paths_field(body.get("paths")))
                self._send_json({"ok": True, "summary": summary, "training": self.runtime.get_training_overview()})
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, status=400)
            return
        if parsed.path == "/api/training/llm":
            try:
                job = self.runtime.start_llm_finetune(body)
                self._send_json({"ok": True, "job": job, "training": self.runtime.get_training_overview()})
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, status=400)
            return
        if parsed.path == "/api/training/activate-llm":
            try:
                summary = self.runtime.activate_llm_deployment(str(body.get("target") or ""))
                self._send_json({"ok": True, "summary": summary, "training": self.runtime.get_training_overview()})
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, status=400)
            return
        if parsed.path == "/api/training/activate-pi":
            try:
                summary = self.runtime.activate_pi_deployment(str(body.get("target") or ""))
                self._send_json({"ok": True, "summary": summary, "training": self.runtime.get_training_overview()})
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, status=400)
            return
        if parsed.path == "/api/training/pi":
            try:
                job = self.runtime.start_pi_detector_finetune(body)
                self._send_json({"ok": True, "job": job, "training": self.runtime.get_training_overview()})
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, status=400)
            return
        if parsed.path == "/api/training/run-all":
            try:
                job = self.runtime.start_full_training_pipeline(body)
                self._send_json({"ok": True, "job": job, "training": self.runtime.get_training_overview()})
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, status=400)
            return
        self._send_json({"ok": False, "error": "Not found"}, status=404)

    def _read_json_body(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        if not raw:
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            return {}

    @staticmethod
    def _paths_field(value: Any) -> list[str]:
        if isinstance(value, str):
            return [value] if value.strip() else []
        if isinstance(value, (list, tuple)):
            return [str(item) for item in value if str(item).strip()]
        return []

    def _send_json(self, payload: Dict[str, Any], status: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _send_frame(self, stream_id: str) -> None:
        try:
            data = self.runtime.frame_bytes(stream_id)
        except Exception:
            data = self.runtime.frame_bytes("local") if stream_id != "local" else b""
        self.send_response(200)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _serve_static(self, path: str) -> None:
        target = "index.html" if path in {"", "/"} else path.lstrip("/")
        candidate = (self.static_root / target).resolve()
        if not str(candidate).startswith(str(self.static_root.resolve())) or not candidate.exists():
            candidate = self.static_root / "index.html"
        content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        data = candidate.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args: Any) -> None:
        return


def serve_dashboard(host: str = "127.0.0.1", port: int = 8765, open_browser: bool = False) -> None:
    runtime = LabDetectorRuntime()
    runtime.set_server_meta(host, port)
    server = DashboardServer(host, port, runtime)
    url = f"http://{host}:{port}"
    runtime._log_info(f"LabDetector Web 控制台已启动: {url}")

    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        runtime.shutdown()


