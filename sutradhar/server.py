"""Tiny stdlib web server for the Sutradhar UI (no framework, no build step)."""

from __future__ import annotations

import json
import os
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .demo import ScriptedLLM, demo_story
from .llm import BharatCodeLLM, LLMError
from .pipeline import analyze, ask

WEB = Path(__file__).with_name("web")
MAX_BODY = 2_000_000
JOBS: dict[str, dict] = {}


def _make_llm(demo: bool):
    return ScriptedLLM() if demo else BharatCodeLLM()


def _run_job(job_id: str, text: str, demo: bool, deep: bool):
    job = JOBS[job_id]

    def prog(frac, msg):
        job["progress"], job["message"] = frac, msg

    try:
        llm = _make_llm(demo)
        job["llm"] = llm
        job["result"] = analyze(text, llm, on_progress=prog, deep=deep)
        job["status"] = "done"
    except Exception as e:  # noqa: BLE001
        job["status"], job["error"] = "error", str(e)


class Handler(BaseHTTPRequestHandler):
    server_version = "Sutradhar"

    def log_message(self, *a):  # quiet
        pass

    def _send(self, code, payload, ctype="application/json"):
        body = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype + ("; charset=utf-8" if "text" in ctype or "json" in ctype else ""))
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_BODY:
            raise ValueError("Manuscript too large (max 2 MB).")
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            return self._send(200, (WEB / "index.html").read_bytes(), "text/html")
        if self.path == "/api/config":
            return self._send(200, {"live": bool(os.environ.get("BHARATCODE_API_KEY"))})
        if self.path == "/api/demo-text":
            return self._send(200, {"text": demo_story()})
        if self.path.startswith("/api/job/"):
            job = JOBS.get(self.path.rsplit("/", 1)[1])
            if not job:
                return self._send(404, {"error": "unknown job"})
            return self._send(200, {k: job.get(k) for k in ("status", "progress", "message", "result", "error")})
        self._send(404, {"error": "not found"})

    def do_POST(self):
        try:
            data = self._body()
            if self.path == "/api/analyze":
                demo = bool(data.get("demo"))
                text = demo_story() if demo else str(data.get("text") or "")
                if not text.strip():
                    return self._send(400, {"error": "Paste a manuscript first."})
                if not demo and not os.environ.get("BHARATCODE_API_KEY"):
                    return self._send(400, {"error": "No API key on this server. Use the demo story, or set BHARATCODE_API_KEY."})
                job_id = uuid.uuid4().hex[:12]
                JOBS[job_id] = {"status": "running", "progress": 0, "message": "Starting", "text": text, "demo": demo}
                if len(JOBS) > 50:
                    JOBS.pop(next(iter(JOBS)))
                threading.Thread(target=_run_job, args=(job_id, text, demo, bool(data.get("deep", True))), daemon=True).start()
                return self._send(200, {"job": job_id})
            if self.path == "/api/ask":
                job = JOBS.get(str(data.get("job")))
                if not job or job.get("status") != "done":
                    return self._send(400, {"error": "Analyse a manuscript first."})
                q = str(data.get("question") or "").strip()[:500]
                if not q:
                    return self._send(400, {"error": "Type a question."})
                return self._send(200, {"answer": ask(q, job["result"], job["text"], job["llm"])})
            self._send(404, {"error": "not found"})
        except (LLMError, ValueError, json.JSONDecodeError) as e:
            self._send(400, {"error": str(e)})


def serve(host="127.0.0.1", port=8000):
    httpd = ThreadingHTTPServer((host, port), Handler)
    live = "live (BharatCode API)" if os.environ.get("BHARATCODE_API_KEY") else "demo only (set BHARATCODE_API_KEY for live)"
    print(f"Sutradhar running on http://{host}:{port}  [{live}]")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")
