"""Local HTTPS edge for Phase 5 integration tests (never a production proxy).

The browser edge serves the built Vue files and routes user APIs through the
session gateway. A separate TLS port sends Worker APIs to Backend directly.
The separate S3 edge preserves the signed Host header for MinIO presigned URLs.
All listeners bind to loopback and require an explicit test certificate.
"""
from __future__ import annotations

import argparse
import http.client
import mimetypes
import ssl
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit


HOP_HEADERS = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
               "te", "trailer", "transfer-encoding", "upgrade"}


class Edge(BaseHTTPRequestHandler):
    server_version = "EpiLocateLocalTestEdge/1"

    def log_message(self, _format, *args):
        # URLs can include S3 signatures; never log request paths or headers.
        pass

    def do_GET(self):
        self.route()

    def do_HEAD(self):
        self.route()

    def do_POST(self):
        self.route()

    def do_PUT(self):
        self.route()

    def do_PATCH(self):
        self.route()

    def do_DELETE(self):
        self.route()

    def route(self):
        if self.server.kind == "s3":
            self.forward(self.server.target)
        elif self.server.kind == "backend":
            self.forward(self.server.backend)
        elif self.path.startswith(("/api/v2/", "/auth/")):
            self.forward(self.server.gateway)
        elif self.command in {"GET", "HEAD"}:
            self.static()
        else:
            self.send_error(404)

    def forward(self, target):
        length = int(self.headers.get("Content-Length", "0"))
        if length > 25 * 1024 * 1024:
            self.send_error(413)
            return
        body = self.rfile.read(length) if length else None
        headers = {key: value for key, value in self.headers.items()
                   if key.lower() not in HOP_HEADERS and key.lower() != "content-length"}
        if body is not None:
            headers["Content-Length"] = str(len(body))
        if self.server.kind != "s3":
            headers["Host"] = f"127.0.0.1:{target}"
        connection = http.client.HTTPConnection("127.0.0.1", target, timeout=120)
        try:
            connection.request(self.command, self.path, body=body, headers=headers)
            response = connection.getresponse()
            payload = response.read()
            self.send_response(response.status)
            for key, value in response.getheaders():
                if key.lower() not in HOP_HEADERS | {"content-length", "server", "date"}:
                    self.send_header(key, value)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(payload)
        except (OSError, http.client.HTTPException):
            self.send_error(502)
        finally:
            connection.close()

    def static(self):
        path = unquote(urlsplit(self.path).path).lstrip("/")
        root = self.server.static_root
        candidate = (root / path).resolve()
        if not candidate.is_relative_to(root):
            self.send_error(404)
            return
        if not candidate.is_file():
            candidate = root / "index.html"
        payload = candidate.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(candidate.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(payload)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=("browser", "backend", "s3"), required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--cert", type=Path, required=True)
    parser.add_argument("--key", type=Path, required=True)
    parser.add_argument("--gateway", type=int, default=8900)
    parser.add_argument("--backend", type=int, default=8899)
    parser.add_argument("--target", type=int, default=59120)
    parser.add_argument("--static-root", type=Path, default=Path("frontend/dist"))
    args = parser.parse_args()
    if args.kind == "browser" and not (args.static_root / "index.html").is_file():
        parser.error("Build frontend/dist first")
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Edge)
    server.kind, server.gateway, server.backend, server.target = args.kind, args.gateway, args.backend, args.target
    server.static_root = args.static_root.resolve()
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(args.cert, args.key)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
