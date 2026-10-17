"""Serve the frozen 64-only MVP with an additive synthetic annotation entry.

The candidate, database copy, API scope and assets remain owned by the existing
demo64 service. This bridge only changes the HTML shell returned by the local
edge so a reviewer can open the separately validated checkerboard workspace.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import signal
import ssl
import subprocess
import sys
import time
from html import escape
from http.server import ThreadingHTTPServer
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from qa import local_mvp_demo64 as demo64
from qa import local_mvp_readonly as readonly

DEFAULT_ANNOTATION_URL = "https://localhost:57171/annotations/"
ENTRY_MARKER = "data-epilocate-annotation-entry"


def annotation_html(raw: bytes, annotation_url: str = DEFAULT_ANNOTATION_URL) -> bytes:
    """Add one accessible entry to the existing app shell, idempotently."""
    parsed_url = urlsplit(annotation_url)
    if (parsed_url.scheme != "https" or parsed_url.hostname != "localhost"
            or parsed_url.port != 57171 or parsed_url.path != "/annotations/"
            or parsed_url.query or parsed_url.fragment):
        raise ValueError("ANNOTATION_URL_OUTSIDE_FIXED_LOCAL_WORKSPACE")
    marker = ENTRY_MARKER.encode("ascii")
    if marker in raw:
        return raw
    href = escape(annotation_url, quote=True)
    block = f"""
<style data-epilocate-annotation-style>
  .epilocate-annotation-entry {{
    position: fixed;
    z-index: 9998;
    right: 16px;
    bottom: 56px;
    box-sizing: border-box;
    width: min(300px, calc(100vw - 32px));
    padding: 14px 14px 13px;
    border: 1px solid #d7dee8;
    border-radius: 10px;
    background: #f8fafc;
    color: #172033;
    box-shadow: 0 8px 20px rgba(15, 23, 42, .06);
  }}
  .epilocate-annotation-entry__top {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    margin-bottom: 7px;
  }}
  .epilocate-annotation-entry__title {{
    font-size: 13px;
    font-weight: 700;
    letter-spacing: .01em;
  }}
  .epilocate-annotation-entry__tag {{
    padding: 3px 7px;
    border: 1px solid #b8d6cb;
    border-radius: 999px;
    color: #17624f;
    background: #edf8f3;
    font-size: 10px;
    font-weight: 700;
    white-space: nowrap;
  }}
  .epilocate-annotation-entry__note {{
    margin: 0 0 10px;
    color: #5c687b;
    font-size: 11px;
    line-height: 1.45;
  }}
  .epilocate-annotation-entry__link {{
    display: inline-flex;
    align-items: center;
    gap: 6px;
    color: #155e75;
    font-size: 12px;
    font-weight: 700;
    text-decoration: none;
  }}
  .epilocate-annotation-entry__link:hover,
  .epilocate-annotation-entry__link:focus-visible {{ text-decoration: underline; }}
  .epilocate-annotation-entry__link:focus-visible {{
    outline: 3px solid #4c91a4;
    outline-offset: 3px;
    border-radius: 2px;
  }}
  body:has(#workspace-navigation) .epilocate-annotation-entry {{
    left: 14px;
    right: auto;
    top: clamp(286px, 44vh, 330px);
    bottom: auto;
    width: 180px;
  }}
  @media (max-width: 720px) {{
    .epilocate-annotation-entry {{
      right: 12px;
      top: auto;
      bottom: 48px;
      width: min(244px, calc(100vw - 24px));
      padding: 11px 12px;
    }}
  }}
  @media (max-width: 720px) {{
    body:has(#workspace-navigation) .epilocate-annotation-entry {{ left: auto; }}
  }}
  [data-theme="dark"] .epilocate-annotation-entry {{
    border-color: #334155;
    background: #182231;
    color: #e6edf5;
    box-shadow: none;
  }}
  [data-theme="dark"] .epilocate-annotation-entry__tag {{
    border-color: #2f7664;
    color: #b6eadb;
    background: #16392f;
  }}
  [data-theme="dark"] .epilocate-annotation-entry__note {{ color: #aab7c8; }}
  [data-theme="dark"] .epilocate-annotation-entry__link {{ color: #8dd6e8; }}
</style>
<aside class="epilocate-annotation-entry" {ENTRY_MARKER}="true" aria-label="医生标注入口">
  <div class="epilocate-annotation-entry__top">
    <span class="epilocate-annotation-entry__title">医生标注</span>
    <span class="epilocate-annotation-entry__tag">合成工作区</span>
  </div>
  <p class="epilocate-annotation-entry__note">棋盘测试影像（非真实 CT）</p>
  <a class="epilocate-annotation-entry__link" href="{href}" target="_blank" rel="noopener noreferrer">
    打开标注工作区 <span aria-hidden="true">&#8599;</span>
  </a>
</aside>
""".encode("utf-8")
    closing = b"</body>"
    return raw.replace(closing, block + closing, 1) if closing in raw else raw + block


class CandidateHTTPServer(ThreadingHTTPServer):
    request_queue_size = 64

    def serve_forever(self, *args, **kwargs):
        self.socket.do_handshake_on_connect = False
        return super().serve_forever(*args, **kwargs)


def edge_child(run: Path, dist: Path, annotation_url: str) -> None:
    config = json.loads((run / "private-config.json").read_bytes())
    from qa.phase5_local_https import Edge

    class BridgeEdge(Edge):
        def route(self):
            if self.command not in {"GET", "HEAD"} and not (
                self.command == "POST" and self.path in {"/auth/login", "/auth/logout"}
            ):
                self.send_error(403, "Read-only local snapshot")
                return
            if self.path.startswith(("/api/v2/workers", "/generated-object/")):
                self.send_error(403)
                return
            return super().route()

        def static(self):
            if self.path.startswith("/mvp/"):
                self.path = self.path[len("/mvp") :]
            if self.path.split("?", 1)[0] in {"/favicon.svg"} or "/assets/" in self.path:
                return super().static()
            raw = readonly.static_html((self.server.static_root / "index.html").read_bytes())
            raw = annotation_html(raw, annotation_url)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(raw)

    server = CandidateHTTPServer(("127.0.0.1", config["ports"]["edge"]), BridgeEdge)
    server.kind = "browser"
    server.backend = config["ports"]["backend"]
    server.gateway = config["ports"]["gateway"]
    server.static_root = dist.resolve()
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    tls.load_cert_chain(run / "tls.crt", run / "tls.key")
    server.socket = tls.wrap_socket(server.socket, server_side=True, do_handshake_on_connect=False)
    server.serve_forever()


def _copy_certificate(source_run: Path, target_run: Path) -> None:
    for name, mode in (("tls.crt", 0o644), ("tls.key", 0o600)):
        target = target_run / name
        shutil.copyfile(source_run / name, target)
        target.chmod(mode)


def serve(candidate: dict, policy: dict, run: Path, dist: Path, annotation_url: str,
          reuse_certificate_from: Path | None = None, existing: bool = False) -> None:
    if existing:
        config_path = run / "private-config.json"
        if not config_path.is_file() or config_path.is_symlink():
            raise ValueError("EXISTING_PRIVATE_CONFIG_REQUIRED")
        config = json.loads(config_path.read_bytes())
        binding = readonly.bound(policy["original_binding"])
        if (config.get("demo64_policy") != policy
                or config.get("source_db") != binding.get("source_db")
                or Path(config.get("source_objects", "")).resolve() != Path(binding["source_objects"]).resolve()
                or config.get("ports") != {"backend": 57590, "gateway": 57591, "edge": 57592}
                or config.get("origin") != "https://127.0.0.1:57592"):
            raise ValueError("EXISTING_RUN_IDENTITY_DRIFT")
        verified = demo64.restrict_config(config, policy)
        if (verified.get("object_sha256") != config.get("object_sha256")
                or verified.get("results") != config.get("results")):
            raise ValueError("EXISTING_RUN_SCOPE_DRIFT")
    else:
        config = readonly.prepare_run(readonly.bound(policy["original_binding"]), run)
        # Keep the public local endpoint stable so an existing browser handoff at
        # 57592 continues to work after the additive bridge is installed.
        config["ports"] = {"backend": 57590, "gateway": 57591, "edge": 57592}
        config["origin"] = "https://127.0.0.1:57592"
        config["environment"]["EPILOCATE_GATEWAY_PUBLIC_ORIGIN"] = config["origin"]
        config["environment"]["EPILOCATE_GATEWAY_BACKEND_ORIGIN"] = "http://127.0.0.1:57590"
        config = demo64.restrict_config(config, policy)
        temp = run / "restricted-config.json"
        readonly.private(temp, config)
        os.replace(temp, run / "private-config.json")
    if reuse_certificate_from:
        _copy_certificate(reuse_certificate_from, run)
    elif not (run / "tls.crt").is_file() or not (run / "tls.key").is_file():
        subprocess.run(
            ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
             "-keyout", str(run / "tls.key"), "-out", str(run / "tls.crt"),
             "-days", "3", "-subj", "/CN=127.0.0.1",
             "-addext", "subjectAltName=IP:127.0.0.1"],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        (run / "tls.key").chmod(0o600)
    processes = []
    logs = []
    previous = {sig: signal.signal(sig, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
                for sig in (signal.SIGINT, signal.SIGTERM)}
    try:
        for kind in ("backend", "gateway"):
            log_name = "restart-" + kind + ".log" if existing else kind + ".log"
            log = (run / log_name).open("xb")
            logs.append(log)
            processes.append(subprocess.Popen(
                [sys.executable, str(Path(demo64.__file__).resolve()), "--child", kind,
                 "--run-directory", str(run), "--dist", str(dist)],
                cwd=ROOT, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1",
                                   OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1",
                                   MKL_NUM_THREADS="1"), stdout=log, stderr=log,
            ))
        edge_log_name = "restart-edge.log" if existing else "edge.log"
        edge_log = (run / edge_log_name).open("xb")
        logs.append(edge_log)
        processes.append(subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "--child", "edge",
             "--run-directory", str(run), "--dist", str(dist),
             "--annotation-url", annotation_url],
            cwd=ROOT, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1",
                               OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1",
                               MKL_NUM_THREADS="1"), stdout=edge_log, stderr=edge_log,
        ))
        import httpx
        deadline = time.monotonic() + 15
        with httpx.Client(verify=str(run / "tls.crt"), trust_env=False, timeout=1) as client:
            while True:
                if any(p.poll() is not None for p in processes):
                    raise RuntimeError("OWN_SERVICE_EXITED")
                try:
                    if (client.get(config["origin"] + "/auth/session").status_code == 401
                            and client.get("http://127.0.0.1:" + str(config["ports"]["backend"])
                                           + "/api/v2/results/" + config["results"][0]).status_code == 401):
                        break
                except httpx.HTTPError:
                    pass
                if time.monotonic() >= deadline:
                    raise TimeoutError("STARTUP_DEADLINE")
                time.sleep(.05)
        ready_name = "bridge-restarted-ready.json" if existing else "bridge-ready.json"
        readonly.private(run / ready_name, {
            "mode": "DEMO64_HISTORICAL_ONLY_WITH_SYNTHETIC_ANNOTATION_ENTRY",
            "model_calls": 0, "worker_started": False,
            "annotation_url": annotation_url,
        })
        print(json.dumps({"url": config["origin"] + "/mvp/", "annotation_url": annotation_url,
                          "run_directory": str(run), "model_calls": 0}), flush=True)
        while True:
            if any(p.poll() is not None for p in processes):
                raise RuntimeError("OWN_SERVICE_EXITED")
            time.sleep(.25)
    except KeyboardInterrupt:
        pass
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)
        for log in logs:
            log.close()
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate")
    parser.add_argument("--candidate-sha")
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--serve-existing", action="store_true")
    parser.add_argument("--run-directory", type=Path)
    parser.add_argument("--dist", type=Path)
    parser.add_argument("--child", choices=("edge",))
    parser.add_argument("--annotation-url", default=DEFAULT_ANNOTATION_URL)
    parser.add_argument("--reuse-certificate-from", type=Path)
    args = parser.parse_args()
    if args.child:
        if not args.run_directory or not args.dist:
            parser.error("child requires run directory and dist")
        edge_child(args.run_directory.resolve(), args.dist.resolve(), args.annotation_url)
        return
    if not args.candidate or not args.candidate_sha:
        parser.error("exact candidate path/SHA required")
    frozen, policy = demo64.checked({"path": args.candidate, "sha256": args.candidate_sha})
    # The frozen candidate declares the dependency-complete local runtime. Use
    # it for the bridge and its child processes so import resolution is bound
    # to the same environment as the validated service.
    runtime_env = frozen.get("runtime", {}).get("environment", {})
    os.environ.update(runtime_env)
    for runtime_path in runtime_env.get("PYTHONPATH", "").split(os.pathsep):
        if runtime_path and runtime_path not in sys.path:
            sys.path.insert(0, runtime_path)
    if not args.serve and not args.serve_existing:
        print(json.dumps({"status": "CANDIDATE_METADATA_PASS", "model_calls": 0,
                          "services": 0, "payload_read": False, "annotation_entry": True}))
        return
    if (not args.run_directory or not args.dist
            or not args.run_directory.resolve().is_relative_to(ROOT / ".local")
            or args.dist.resolve() != Path(frozen["dist"]).resolve()):
        parser.error("new task-local run directory and bound dist required")
    if args.serve_existing and not args.run_directory.resolve().is_dir():
        parser.error("existing task run directory required")
    if args.serve and args.run_directory.resolve().exists():
        parser.error("new task run directory must not already exist")
    serve(frozen, policy, args.run_directory.resolve(), args.dist.resolve(), args.annotation_url,
          args.reuse_certificate_from.resolve() if args.reuse_certificate_from else None,
          existing=args.serve_existing)


if __name__ == "__main__":
    main()
