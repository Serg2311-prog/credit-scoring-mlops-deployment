"""Tiny Prometheus exporter for aggregated Stage-6 monitoring JSON artifacts."""

from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from src.monitoring.prometheus_export import (
    render_prometheus_text,
    resolve_monitoring_export,
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
            export = resolve_monitoring_export(root=root)
            body = render_prometheus_text(
                export.gauges,
                status=export.status,
                detail=export.detail,
            ).encode("utf-8")
            # Always 200: status gauge encodes unavailable/stale/invalid.
            # Drift value series are omitted unless status=valid (no fake zeros).
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args) -> None:  # noqa: A003
            return

    HTTPServer((args.host, args.port), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
