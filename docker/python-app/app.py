#!/usr/bin/env python3
"""lab-app: tiny LAB service for the docker-containers-lab project.

Standard library only -- no pip installs, so the image stays small and the
build stays reproducible. Exposes:

  GET /         small HTML landing page
  GET /health   JSON liveness probe -> {"status": "ok", ...}
  GET /metrics  Prometheus exposition format (request counter + up gauge)

Every request is logged to stdout so `docker logs` (and scripts/collect-logs.py)
can pick it up. Never log secrets here: nothing in this app reads credentials.
"""
import json
import os
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("APP_PORT", "8000"))
HOSTNAME = socket.gethostname()
STARTED_AT = time.time()
REQUEST_COUNT = 0
COUNT_LOCK = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    server_version = "lab-app/1.0"

    def log_message(self, fmt, *args):
        # Standard request log line on stdout. (BaseHTTPRequestHandler already
        # includes the request line in fmt/args -- don't add it twice.)
        print(
            f'{self.client_address[0]} - - [{self.log_date_time_string()}] '
            f'{fmt % args}',
            flush=True,
        )

    def _send(self, code, body, ctype="application/json"):
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _count(self):
        global REQUEST_COUNT
        with COUNT_LOCK:
            REQUEST_COUNT += 1
            return REQUEST_COUNT

    def do_GET(self):
        n = self._count()
        if self.path == "/health":
            self._send(
                200,
                json.dumps({"status": "ok", "host": HOSTNAME, "requests": n}),
            )
        elif self.path == "/metrics":
            uptime = int(time.time() - STARTED_AT)
            body = (
                "# HELP lab_app_up 1 when the app is serving traffic\n"
                "# TYPE lab_app_up gauge\n"
                "lab_app_up 1\n"
                "# HELP lab_app_requests_total Total HTTP requests served\n"
                "# TYPE lab_app_requests_total counter\n"
                f"lab_app_requests_total {n}\n"
                "# HELP lab_app_uptime_seconds Seconds since process start\n"
                "# TYPE lab_app_uptime_seconds gauge\n"
                f"lab_app_uptime_seconds {uptime}\n"
            )
            self._send(200, body, "text/plain; version=0.0.4")
        elif self.path == "/":
            self._send(
                200,
                "<html><body><h1>lab-app</h1>"
                "<p>LAB container is up. Try <a href='/health'>/health</a> "
                "or <a href='/metrics'>/metrics</a>.</p></body></html>",
                "text/html",
            )
        else:
            self._send(404, json.dumps({"error": "not found"}))


def main():
    print(f"lab-app starting on 0.0.0.0:{PORT} (host={HOSTNAME})", flush=True)
    # NOTE: binding 0.0.0.0 is correct *inside* the container. The container's
    # network namespace is isolated; what the outside world can reach is
    # controlled by `ports:` in compose, not by the bind address here.
    # See docs/networking.md.
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
