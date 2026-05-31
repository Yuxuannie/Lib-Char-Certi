"""Stdlib HTTP control server for the Lib-Char-Certi console.

Serves the self-contained console HTML and a small JSON API. No third-party deps
(air-gap safe). Binds localhost by default; single user, no auth.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from . import runs

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TEMPLATE = _REPO_ROOT / "gui" / "certi_console.html"


def _console_html() -> str:
    if _TEMPLATE.is_file():
        html = _TEMPLATE.read_text(encoding="utf-8")
        inject = "<script>window.CERTI_API=true;</script>"
        return html.replace("</head>", inject + "\n</head>", 1) if "</head>" in html else inject + html
    return "<!doctype html><meta charset='utf-8'><title>CERTI</title><h1>console template missing</h1>"


def make_handler(manager, runs_root: Path):
    class Handler(BaseHTTPRequestHandler):
        server_version = "CertiConsole/0.1"

        def log_message(self, *args):  # quiet by default
            pass

        def _send(self, code: int, body: Any, ctype: str = "application/json") -> None:
            data = body.encode("utf-8") if isinstance(body, str) else body
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _json(self, code: int, obj: Any) -> None:
            self._send(code, json.dumps(obj), "application/json")

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path in ("/", "/index.html"):
                return self._send(200, _console_html(), "text/html; charset=utf-8")
            if path == "/api/history":
                return self._json(200, {"index": runs.read_index(runs_root)})
            if path == "/api/status":
                return self._json(200, {"jobs": manager.all_status()})
            if path.startswith("/api/batch/"):
                rec = runs.read_run_record(runs_root, path[len("/api/batch/"):])
                return self._json(200, rec) if rec else self._json(404, {"error": "batch not found"})
            if path.startswith("/api/status/"):
                st = manager.status(path[len("/api/status/"):])
                return self._json(200, st) if st else self._json(404, {"error": "unknown job"})
            return self._json(404, {"error": "not found"})

        def do_POST(self):
            path = self.path.split("?", 1)[0]
            if path == "/api/run":
                try:
                    n = int(self.headers.get("Content-Length", "0") or "0")
                    body = json.loads(self.rfile.read(n) or b"{}")
                except (ValueError, json.JSONDecodeError):
                    return self._json(400, {"error": "invalid JSON body"})
                try:
                    return self._json(200, {"id": manager.submit(body)})
                except ValueError as exc:
                    return self._json(400, {"error": str(exc)})
            return self._json(404, {"error": "not found"})

    return Handler


def serve(runs_root: Any, port: int = 8765, host: str = "127.0.0.1",
          batch_concurrency: int = 2, liberate_budget: int = 4):
    from .executor import JobManager

    import socket

    runs_root = runs.resolve_runs_root(runs_root)
    manager = JobManager(runs_root, batch_concurrency, liberate_budget)
    httpd = ThreadingHTTPServer((host, port), make_handler(manager, runs_root))
    print(f"CERTI console: http://localhost:{port}")
    print(f"  open this in a browser ON THE SAME HOST (this host: {socket.gethostname()})")
    print(f"  runs_root={runs_root}  batch_concurrency={batch_concurrency}  liberate_budget={liberate_budget}")
    print("  Ctrl-C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopping...")
    finally:
        manager.shutdown()
        httpd.server_close()
    return manager
