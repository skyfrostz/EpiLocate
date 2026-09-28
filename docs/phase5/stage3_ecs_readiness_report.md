# EpiLocate P1 Phase 5 — Stage 3 ECS readiness audit

## Scope and evidence boundary

- Audit time: 2026-09-28 11:14 Asia/Shanghai (03:14 UTC); local repository inspection only.
- Worktree: `/Users/skyfrost/Documents/Techniques/EpiLocate-p1-phase5-dual-mode-server-demo`; branch `codex/p1-phase5-dual-mode-server-demo`; starting clean HEAD `e74f98432019eb46691e085b957fecb8e23ca1a3`.
- Actual ECS operating system, architecture, CPU, RAM, swap, disks, mounted filesystems, ports, services, TLS, Review Server state, and available backup space: **待 ECS 只读核验**.
- No ECS connection, public-domain probe, service change, deployment, merge, or push occurred in Stage 3. Repository templates and Stage 2 local evidence are not observations of the running ECS.
- Decision: deployment readiness is **not established**. The separate ECS read-only authorization and safe access method, actual measurements, old-service recovery evidence, and production configuration remain gates before a Stage 4 deployment approval.
- Stage 3 changes: this report and `docs/phase5/stage4_deployment_plan.md` only; no application, protocol, checkpoint, service or server file was changed.

Local read-only checks actually run: `git branch --show-current`, `git rev-parse HEAD`, `git status --short --branch`, `rg --files`, targeted `rg -n` and `sed -n` against the files below, `shasum -a 256` on the local frozen checkpoint, and `du -sh` on that checkpoint and `frontend/dist`. The local hash matched the Stage 2 record. The command block later in this document is a **proposed ECS checklist**, not executed evidence.

## Local materials and status

| Item | Current repository evidence | Classification / deployment gap |
| --- | --- | --- |
| Session gateway | `session_gateway/README.md`, `app.py`, `manage.py`: `uvicorn session_gateway.app:create_app --factory`; server-side Backend token mapping; Secure, HttpOnly, SameSite Strict session cookie; CSRF and login throttling; logout, expiry and revocation. Stage 2 exercised two accounts. | Implemented and locally verified. Production origin, account/key/session files, process supervision and trusted TLS remain unverified. |
| Vue frontend | `frontend` builds via `npm run build`; browser API should use same-origin `VITE_API_BASE_URL=/api/v2`. Stage 2 browser flow and build passed. | Build verified locally; immutable production artifact, static-serving headers and dependency review not complete. The example Backend env's cross-origin frontend URL is unsuitable for this gateway topology. |
| Backend v2 | `uvicorn backend_v2.api.app:app`, PostgreSQL-backed user credentials and ownership checks, private MinIO access. Stage 2 live API/storage reread passed. | Implemented locally. Production service unit, explicit health/readiness endpoints and public debug-route policy are missing. Backend FastAPI currently enables `/docs`, `/redoc`, `/openapi.json` by default; ingress must not publish them. |
| PostgreSQL | Alembic revisions `0001_initial_schema`, `0002_result_metadata_and_assets`, `0003_user_credentials`; `backend_v2.scripts.validate_migrations` checks 14 required tables. | Migration path exists; target DB, volume, backup/restore and upgrade execution are unverified. README's older table count is stale. |
| MinIO | Private bucket, signed 300-second object GET for Worker input, Backend-authenticated result asset routes; Backend defaults to seven-day DICOM input retention. Stage 2 PostgreSQL/MinIO round-trip passed. | Local behavior verified; target private binding, matching object lifecycle rule, encryption mode, volume backup and restore are unverified. `backend_v2/docker-compose.production-like.yml` is a local example, not a production release: placeholder secrets, mutable image tag, incomplete health checks and lifecycle-init failure can be hidden by `|| true`. |
| CPU Worker | `deploy/run_server_cpu_worker.sh` loads a mode-0600 env file, forces `WORKER_DEVICE=CPU`, then executes existing `python -m worker`; `docs/phase5/server_cpu_worker_runbook.md` documents provisioning. | Independent real CPU Worker locally verified. Linux dependency lock, target process unit, TLS edges and capacity are not verified. Existing `CUDA`/`AUTO` modes and Worker/API protocol remain. |
| FrozenBaseline | Worker checks the checkpoint SHA-256 and uses the existing adapter. Local checkpoint hash: `548b39b9a799a4cbf56982c569d752c2e37ce4ac005089b0339a6194a3cad734`. | Real local CPU inference verified; deployment artifact hash and Linux CPU PyTorch compatibility must be checked on target. Do not transfer the macOS virtualenv or research data. |
| Sweeper | Separate `python -m backend_v2.workers.sweeper` process, 15-second cadence. Stage 2 lease/retry recovery passed. | Exists and locally verified; production supervision and monitoring missing. |
| Review Server | Repository has `epilocate_review_server/deploy/{nginx.conf,epilocate-review.service}` and `README_DEPLOY.md`. Template uses `project.xbstu.com`, old app loopback port 8765, SQLite under `/var/lib/epilocate-review`, release symlink under `/opt/epilocate-review`. | Historical template only. Actual ECS paths, package, running status, data, configuration, backup and recovery ability are **待 ECS 只读核验**. Do not stop it or copy its live SQLite file as a backup. |
| Observability | Worker suppresses request INFO logs that could reveal signed URL query strings; service logging uses Python/systemd-compatible stdout. | No complete production log retention, secret-redaction review, startup probes or alerting configuration exists. |

The current repository has no new-system production Nginx site file, systemd units, pinned data-service image manifests, or complete health checks. The Stage 2 loopback TLS proxy in `qa/phase5_local_https.py` is test tooling. No parallel Documentation Codex `AGENTS.md`, `docs/project/ITERATION_HISTORY.md`, or `ENGINEERING_JOURNAL.md` was present in this worktree at audit time; this report records the Stage 3 work without editing another worktree.

## Stage 2 evidence relevant to capacity, not ECS sizing

Stage 2 ran on macOS ARM, Apple M5 Pro, 18 logical CPUs and 24 GiB RAM. Its independent CPU Worker completed Prediction and 16/32/64 px Occlusion with `LIVE_CASE`, nine PNG assets and 729/169/36 positions; Gateway/Backend 21, Worker 29 and Frontend 36 tests passed, and Frontend built. Two local Occlusion jobs took 9.68 and 9.43 seconds from first claim to finish. One sampled Worker RSS was 1,380,352 KiB; it is **not peak memory**. The checkpoint file alone is about 128 MiB, and the macOS research virtualenv was about 1.2 GiB; neither number determines Linux installation size or ECS headroom. Local TLS was self-signed. No NVIDIA/CUDA hardware was tested. Details and sanitized evidence are in [Stage 2 report](stage2_cpu_worker_e2e_report.md).

Until ECS CPU/RAM/storage and live process use are measured, the safe initial design is one CPU Worker and one active attempt, with the existing 15-second heartbeat, 90-second lease and configured retry policy. Do not claim a task-throughput or latency service level from the M5 Pro results. Stage 4 must measure model-load peak, Prediction/Occlusion peak RSS, elapsed times, multiuser queue, heartbeat stability, volume growth and service coexistence on ECS before public cutover. If CPU pressure, OOM risk or disk headroom prevents safe coexistence, report a blocker and evaluate a separate CPU host or smaller controlled capacity; do not silently relax the frozen protocol.

| Capacity component | Current numeric evidence | ECS decision still required |
| --- | --- | --- |
| Frozen checkpoint / Vue build | Local files approximately 128 MiB / 5.5 MiB | Add reviewed Linux wheels, release history and backup copies; confirm target architecture and free space. |
| Worker inference | One local RSS sample approximately 1.32 GiB; local time is not transferable | Measure Linux peak RSS/CPU and 16/32/64 px Occlusion duration under concurrent data services. |
| PostgreSQL, MinIO, Gateway, Backend, Sweeper, old Review Server | No ECS usage measurement | Reserve aggregate RAM/CPU plus OS and page-cache headroom; stage with the old service active only if safe. |
| User data, logs and backups | Per-DICOM and per-heatmap size vary; no ECS volume inventory | Estimate growth as retained uploaded DICOM bytes + nine heatmaps per completed Occlusion + DB/session/logs + versioned backups, then measure real samples and set retention/alerts. |

## Security and routing review

- Browser origin: HTTPS `project.xbstu.com` is the **target**. The current live TLS certificate, Nginx routing and validity are **待 ECS 只读核验**. Frontend `/auth/*` and browser `/api/v2/*` must traverse the Gateway. The browser must never receive a Backend Bearer token. Backend ownership checks remain authoritative.
- Worker origin: the on-host Worker needs a separate HTTPS route to Backend `/api/v2/workers/*`. The public browser route must deny this path; the current gateway already rejects browser Worker calls. `BACKEND_URL` cannot be plain HTTP because `WorkerConfig` enforces HTTPS. A loopback-only TLS route with hostname/IP-matching certificate and trusted CA is a proposed production solution, pending target verification.
- Signed MinIO input: the Backend's `EPILOCATE_V2_S3_PUBLIC_ENDPOINT` signs an HTTPS URL for Worker download. Backend `EPILOCATE_V2_S3_ENDPOINT` can remain private HTTP. The signed Host/path/query must survive the private TLS proxy unchanged; validate SigV4 against target MinIO. Do not put signed URLs, query strings, credentials, tokens or DICOM data in Nginx/systemd/app logs. MinIO bucket and PostgreSQL/MinIO ports remain private.
- Browser session and writes: retain gateway `Secure; HttpOnly; SameSite=Strict`, CSRF header and Origin check, rate-limited login, expiry/revocation and server-side token files. Production secret and session file permissions must be checked. `EPILOCATE_V2_ALLOW_ENV_TOKENS=false` is required in production.
- Debug/error boundary: Gateway disables its own OpenAPI UI; Backend does not. Deny Backend `/docs`, `/redoc`, `/openapi.json` at every public ingress and prevent direct Backend access. Check sanitized error responses and no secret-bearing URLs in browser/history/referrer or access logs. Preserve an appropriate Referrer-Policy after reviewing the old site's template.
- Current security concerns needing release review: the local Compose example uses `change-me` and `minio/minio:latest`; its lifecycle setup can mask failure. Frontend README records prior transitive advisories, but current package audit was not rerun in Stage 3. Pin, review and validate actual production dependencies and images before release.

## Proposed ECS read-only audit command list — **not executed**

Execute only after separate authorization, from the approved access path, with output stored privately. The operator should remove hostnames, public IPs, usernames and service identifiers as needed before sharing evidence. No command below changes service state, reads a secret value, or prints application data. Missing packages/paths should be reported as absent; do not install them.

```sh
date -Is
uname -m
cat /etc/os-release
lscpu
nproc
free -h
swapon --show --noheadings
df -hT
lsblk -o NAME,SIZE,FSTYPE,MOUNTPOINTS,TYPE
findmnt -rn -o TARGET,SOURCE,FSTYPE,OPTIONS
command -v docker
docker version --format '{{.Server.Version}}'
docker compose version
docker ps --format '{{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'
docker stats --no-stream --format '{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}'
docker volume ls --format '{{.Name}}'
command -v nginx
nginx -v
systemctl show epilocate-review -p LoadState -p ActiveState -p SubState -p FragmentPath -p ExecMainPID -p MemoryCurrent --no-pager
systemctl list-units --type=service --state=running --no-pager --plain
ss -H -lntup
readlink -f /opt/epilocate-review/current
readlink -f /etc/nginx/sites-enabled/epilocate-review.conf
stat -c '%n %s bytes %a %U:%G %y' /var/lib/epilocate-review/review.sqlite3 /etc/epilocate-review/epilocate-review.env /etc/nginx/sites-enabled/epilocate-review.conf
du -sh /var/lib/epilocate-review /opt/epilocate-review /var/log/nginx /var/log/journal
openssl x509 -in /etc/letsencrypt/live/project.xbstu.com/cert.pem -noout -dates -fingerprint -sha256
journalctl --disk-usage
```

The listed paths/Review service name come from repository templates; verify the actual service and path names first and substitute them. `docker` and `nginx` commands are conditional on installation and permission. The `stat`/`du` results provide size and metadata, not backup validation. `ss` and Docker output can disclose infrastructure metadata; keep raw output private. Review the effective Nginx **route summary** manually after authorization using a redacted copy limited to `listen`, `server_name`, `location`, `proxy_pass`, TLS certificate **path**, and access-log policy; do not publish full `nginx -T`, private-key contents, complete service environment, container inspect, database rows, or live logs. Use `stat` to check permissions on secret files and the TLS key, never `cat` their contents. Record the old SQLite file/WAL location, release target, media directory and mount capacity as metadata only. The former Review Server `manage.py snapshot-db` writes a new file and belongs to the approved backup stage, **not** this read-only audit.

## Gates and handoff

1. Obtain separate ECS read-only authorization and safe access method. Capture the actual system/resource/port/TLS/Review evidence above, including other-service usage and backup destination capacity. Until then all ECS fields in this report remain **待 ECS 只读核验**.
2. Demonstrate the old Review Server can be restored: identify current package, configuration, SQLite and WAL, media, backup method and an isolated restoration check. An unverified old-service recovery path blocks cutover.
3. Decide target Linux architecture and package/runtime versions; pin compatible CPU PyTorch and data images, measure artifact size, checkpoint hash and model-load/inference peaks. Confirm disk for releases, database, private objects, logs and independent backups.
4. Prepare and review production Gateway/Backend/Worker/Sweeper/data-service units, private TLS routes, Nginx policy, secrets, lifecycle and health checks. These are **not yet implemented** in this worktree.
5. Review the conditional [Stage 4 deployment and rollback plan](stage4_deployment_plan.md). Actual deployment, Review Server stop and domain cutover each require their stated separate approvals. GPU AI Node preservation is a code/protocol property; GPU machine acceptance remains outstanding.
