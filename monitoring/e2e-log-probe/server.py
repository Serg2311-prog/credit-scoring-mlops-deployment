"""Test-only ERROR log emitter for Loki ruler E2E (not part of production API)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path in ("/health", "/-/healthy", "/"):
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"ok")
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self) -> None:  # noqa: N802
        if self.path.rstrip("/") != "/error":
            self.send_response(404)
            self.end_headers()
            return
        _ = self.rfile.read(int(self.headers.get("Content-Length", "0") or 0))
        payload = {
            "timestamp": _utc(),
            "level": "ERROR",
            "log_level": "ERROR",
            "service": "e2e-log-probe",
            "logger": "e2e_log_probe",
            "message": "BLOCK8_CONTROLLED_ERROR_LOG synthetic incident (no PII)",
            "request_id": "block8-e2e-controlled-error",
            "endpoint": "/error",
            "status_code": 500,
        }
        # stdout JSON → Alloy docker scrape → Loki (same pipeline as API logs).
        print(json.dumps(payload, ensure_ascii=False), flush=True)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status":"logged"}')

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


if __name__ == "__main__":
    HTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
