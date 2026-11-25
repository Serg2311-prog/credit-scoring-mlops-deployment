"""Tiny Prometheus exporter for aggregated Stage-6 monitoring JSON artifacts."""

from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from src.monitoring.prometheus_export import (
    MonitoringArtifactsUnavailable,
    collect_monitoring_gauges,
    render_prometheus_text,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=9108)
    parser.add_argument(
        "--artifacts-root",
        default=None,
        help="Override artifacts/monitoring root",
    )
    args = parser.parse_args()
    root = Path(args.artifacts_root) if args.artifacts_root else None

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path.rstrip("/") in ("/health", ""):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"ok")
                return
            if self.path.rstrip("/") != "/metrics":
                self.send_response(404)
                self.end_headers()
                return
            try:
                gauges = collect_monitoring_gauges(root=root)
                body = render_prometheus_text(gauges).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; version=0.0.4")
                self.end_headers()
                self.wfile.write(body)
            except MonitoringArtifactsUnavailable as exc:
                # Do not invent zeros — expose scrape failure clearly.
                msg = f"monitoring_artifacts_unavailable {exc}".encode("utf-8")
                self.send_response(503)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(msg)

        def log_message(self, format: str, *args) -> None:  # noqa: A003
            return

    HTTPServer((args.host, args.port), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
