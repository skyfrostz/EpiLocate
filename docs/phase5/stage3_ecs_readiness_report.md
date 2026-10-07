# EpiLocate P1 Phase 5 — Stage 3A/3B ECS readiness audit

## Stage 3B: actual ECS read-only audit (2026-09-28)

**Audit window:** 12:03–12:07 Asia/Shanghai. The owner separately authorized one SSH read-only audit. Local `ssh -G epilocate` resolved to the owner-specified host, account and port; no ProxyCommand/ProxyJump or agent forwarding was configured. The owner supplied the ECS ED25519 **server** public-key fingerprint in response to the trusted-channel verification request; it matched the existing local `known_hosts` record. This task did not operate the owner's independent channel. Connections used `BatchMode=yes`, `StrictHostKeyChecking=yes`, no TTY and no forwarding. Remote `hostname`, `whoami` and the internal IPv4 matched the owner's supplied identity before other commands ran. The report deliberately omits the public IP, full host/user identifiers and raw private network output.

**Observed system and capacity (one time-point, not a peak or inference benchmark):**

| Item | Actual read-only evidence | Judgment |
| --- | --- | --- |
| OS / CPU | Ubuntu 24.04.4 LTS, `x86_64`, KVM virtual machine; Intel Xeon Platinum exposed as **2 logical vCPUs** (one core with two threads in `lscpu`), `nproc=2`. | Physical host share and sustained compute entitlement cannot be inferred. `/sys/fs/cgroup/cpu.max` was absent, so no quota reading was obtained. |
| RAM / swap | 3.5 GiB total, about 2.7 GiB `available` at audit time; 4.0 GiB swap, unused in the sample. | Full-stack plus CPU Worker coexistence is **high risk and unproven**. Swap is not acceptable evidence of enough inference memory. |
| Load / processes | Load averages 0.36/0.11/0.03; three `vmstat` samples had no swap in/out. Review Server, Gradio, Aid site and Nginx were active. | A few seconds of idle sampling do not establish peak headroom or multiuser throughput. |
| Disk / mounts | One 50 GB virtual disk, root `ext4` filesystem 49 GiB with 39 GiB available (18% used); no separate persistent data/backup mount appeared in `lsblk`/`findmnt`. | Space can hold a staging copy in principle, but same-disk copies do not provide independent recovery. Need an approved off-host or separate-volume backup/restore target. |
| Logs | Nginx logs about 1.8 MiB; journal about 24–25 MiB. | Retention and growth have not been load tested. |
| Candidate ports | `ss -H -lnt` showed public 80/443 and SSH 22; loopback 8000, 4110, 8765, 8766. Proposed 8890, 8891, 9443, 9444, 5432 and 9000 were **not listening at that instant**. | This is not a reservation. No service was stopped or started to free a port. Port owners were not queried with the disallowed privileged variant. |
| Data services | No PostgreSQL/MinIO listener or running unit appeared in the permitted `ss`/`systemctl` results. | Installation, Docker/Compose version, images and inactive units remain **unconfirmed** because Docker management interface calls were explicitly forbidden. |

The Stage 2 Worker had only a local **sampled**, non-peak RSS of about 1.32 GiB on an 18-logical-CPU M5 Pro. Subtracting that number from the ECS's instantaneous available memory would be an invalid capacity proof: Linux model peak, PostgreSQL, MinIO, Gateway, Backend, Sweeper, existing services, page cache and burst load all remain unmeasured. A single Worker/single attempt is the maximum initial **proposal**, subject to Stage 4A server measurement. No model inference or pressure test was run in Stage 3B. A capacity upgrade or separate compute host may be needed; do not shrink the frozen algorithm or remove required services to fit this instance.

**Existing Review Server, Nginx and TLS:**

| Check | Verified fact | Limit / next gate |
| --- | --- | --- |
| Old service | `epilocate-review.service` was `active/running`; systemd unit path `/etc/systemd/system/epilocate-review.service`, environment **file path** `/etc/epilocate-review/epilocate-review.env`. Current release symlink resolved under `/opt/epilocate-review/releases/`. | systemd supervision is verified; the exact `ExecStart` line was not read under this scope. No start/stop/reload or environment **values** read. Restore ability not proven. |
| Old data | SQLite file at `/var/lib/epilocate-review/review.sqlite3`, 139,264 bytes at audit time. No `review.sqlite3-wal` at that instant. `/var/lib/epilocate-review` totaled about 280 KiB; media bundle about 457 MiB; full old install about 517 MiB, including about 60 MiB virtualenv. | Absence of a WAL at one instant does not authorize a raw live-file copy. No snapshot, backup or isolated restore was executed. Existing exports directory was about 4 KiB. |
| Old access permissions | Data directory mode 750; environment file mode 640; media bundle mode 750. SQLite file mode 644 inside the restricted data directory. | Review permission model before Stage 4A backup; no file contents read. |
| Public site | Nginx 1.24.0 active. Actual enabled `project.xbstu.com` site listens on 80/443 and proxies to loopback 8765; another enabled Aid site shares Nginx and proxies to loopback 8766. Old site's `client_max_body_size` is 64k and has a same-origin referrer policy. | Preserve the other site. A new DICOM upload route requires a separately reviewed size limit and site-only cutover in Stage 4B. No Nginx config was changed or tested with `nginx -t`. |
| Certificate / response | Existing Let's Encrypt certificate for the target domain was valid during audit, expiring 2026-12-23 13:00:43 UTC; `certbot.timer` was listed. The TLS private key **target metadata** was mode 600, root-owned. A loopback-resolved HTTPS request to the old `/healthz` returned HTTP 200 with certificate verification result 0. | Renewal success and new-site TLS behavior remain untested. No private key contents or HTTP response body were read. |

**Network and security feasibility:** Nginx and the currently unused candidate loopback ports make the proposed separate private Worker/API and signed-MinIO TLS listeners technically plausible, **not verified working**. Stage 4A must build and test a SAN-matching certificate/CA, `WORKER_CA_CERT`, preserved SigV4 Host/port/path/query, and log redaction without disabling TLS validation. Browser Gateway security properties were validated locally in Stage 1/2 code and tests; the new Gateway is not deployed here, so ECS session cookies, CSRF, login throttling, ownership and `/docs` denial cannot yet be live-verified. Current Nginx has an access log directive with no redaction verified; a new signed-object edge must prevent signed query strings from reaching logs. Host firewall rules and cloud security-group state remain **unverified**: the owner barred the proposed `sudo -n` firewall command and no control-plane evidence was supplied.

**Actual commands and exceptions:** the following were executed only as remote read-only checks after the identity gate. The SSH wrapper used the strict flags above. Raw command output stayed in this task; this report records only sanitized conclusions.

| Commands actually run | Purpose / result |
| --- | --- |
| Local `ssh -G epilocate`, `ssh-keygen -F epilocate -l`, `ssh-keygen -F <owner-specified-host> -l`; remote `hostname`, `whoami`, `ip -o -4 addr show scope global`, `date -Is` | Effective route, existing host key, owner-confirmed fingerprint, target identity and audit time. |
| `cat /etc/os-release`, `uname -m`, `lscpu`, `nproc`, `cat /sys/fs/cgroup/cpu.max` | OS/CPU. The last command failed because that file was absent; it is **not** a passed quota check. |
| `free -h`, `swapon --show --noheadings`, `uptime`, `vmstat 1 3`, `ps -eo pid,comm,%cpu,rss --sort=-rss \| head -n 20` | Memory, swap, load and one-time process samples; no process arguments printed. |
| `df -hT`, `lsblk -o NAME,SIZE,FSTYPE,MOUNTPOINTS,TYPE`, `findmnt -rn -o TARGET,SOURCE,FSTYPE,OPTIONS`, `df -hT <old-data-and-release-paths>` | Disk size, free space and mounts. |
| `systemctl list-units --type=service --state=running --no-pager --plain`, `systemctl show <Review/Gradio/Aid/Nginx-unit> -p LoadState -p ActiveState -p SubState -p FragmentPath -p ExecMainPID -p MemoryCurrent -p EnvironmentFiles --no-pager`, `systemctl list-timers --all --no-pager` | Running services, unit/config-file paths, current memory and renewal timer; no environment values. |
| `ss -H -lnt`, `nginx -v`, `journalctl --disk-usage` | Listener snapshot, Nginx version and journal size. |
| `rg --files <Nginx-dirs>` then `find <Nginx-dirs> -maxdepth 1 ... -print`, targeted `grep -En` for Nginx route/header/log directives | `rg` was absent; the approved `find`/targeted grep fallback identified the two enabled sites and non-secret route metadata. No full `nginx -T`. |
| `readlink -f <old-release-and-site-paths>`, `stat -c ... <SQLite/WAL/env/site/key/dirs>`, `stat -L -c ... <TLS-key>`, `du -sh <old-data/release/media/log/exports-paths>` | Old-service paths, modes and sizes only. An initial `stat` attempt had shell-quoting errors; it was corrected and rerun. Missing WAL was recorded as absent at audit time. |
| `openssl x509 -in <public-cert> -noout -dates -issuer -subject -fingerprint -sha256`, `curl --max-time 5 --resolve <target-domain>:443:127.0.0.1 -o /dev/null -sS -w ... https://<target-domain>/healthz` | Public-certificate metadata and current old-site HTTPS health; no body, cookie or key output. |

**Not executed / unavailable:** Docker or Compose management calls, `sudo -n` commands, firewall rule listing, cloud security-group inspection, full logs, DB queries, patient/media reads, environment-value reads, private-key reads, backup/snapshot/restore, software installation, service or Nginx changes, model inference, GPU testing, and any Stage 4 action. Docker/Compose availability, effective firewall policy, Linux Worker dependency compatibility, real CPU peak/runtime, MinIO SigV4 proxy, off-host backup and old-service restoration are **deployment gates**. The read-only audit can support a conditional Stage 4A proposal, but does **not** approve Stage 4A or Stage 4B.

## Stage 3A: local-material audit and original evidence boundary

- Audit time: 2026-09-28 11:14 Asia/Shanghai (03:14 UTC); local repository inspection only.
- Worktree: `LOCAL_WORKTREE/EpiLocate-p1-phase5-dual-mode-server-demo`; branch `codex/p1-phase5-dual-mode-server-demo`; starting clean HEAD `e74f98432019eb46691e085b957fecb8e23ca1a3`.
- At Stage 3A, actual ECS operating system, architecture, CPU, RAM, swap, disks, mounted filesystems, ports, services, TLS, Review Server state and backup space were **待 ECS 只读核验**. Stage 3B results are recorded above.
- No ECS connection, public-domain probe, service change, deployment, merge or push occurred in **Stage 3A**. Repository templates and Stage 2 local evidence were not observations of the running ECS.
- The Stage 3A decision was that deployment readiness was **not established**. Stage 3B has since supplied bounded read-only observations, but restore, peak capacity and production configuration remain gates.
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

- Browser origin: HTTPS `project.xbstu.com` is the **target**. At Stage 3A the live TLS certificate and Nginx routing were **待 ECS 只读核验**; Stage 3B findings are above. Frontend `/auth/*` and browser `/api/v2/*` must traverse the Gateway. The browser must never receive a Backend Bearer token. Backend ownership checks remain authoritative.
- Worker origin: the on-host Worker needs a separate HTTPS route to Backend `/api/v2/workers/*`. The public browser route must deny this path; the current gateway already rejects browser Worker calls. `BACKEND_URL` cannot be plain HTTP because `WorkerConfig` enforces HTTPS. A loopback-only TLS route with hostname/IP-matching certificate and trusted CA is a proposed production solution, pending target verification.
- Signed MinIO input: the Backend's `EPILOCATE_V2_S3_PUBLIC_ENDPOINT` signs an HTTPS URL for Worker download. Backend `EPILOCATE_V2_S3_ENDPOINT` can remain private HTTP. The signed Host/path/query must survive the private TLS proxy unchanged; validate SigV4 against target MinIO. Do not put signed URLs, query strings, credentials, tokens or DICOM data in Nginx/systemd/app logs. MinIO bucket and PostgreSQL/MinIO ports remain private.
- Browser session and writes: retain gateway `Secure; HttpOnly; SameSite=Strict`, CSRF header and Origin check, rate-limited login, expiry/revocation and server-side token files. Production secret and session file permissions must be checked. `EPILOCATE_V2_ALLOW_ENV_TOKENS=false` is required in production.
- Debug/error boundary: Gateway disables its own OpenAPI UI; Backend does not. Deny Backend `/docs`, `/redoc`, `/openapi.json` at every public ingress and prevent direct Backend access. Check sanitized error responses and no secret-bearing URLs in browser/history/referrer or access logs. Preserve an appropriate Referrer-Policy after reviewing the old site's template.
- Current security concerns needing release review: the local Compose example uses `change-me` and `minio/minio:latest`; its lifecycle setup can mask failure. Frontend README records prior transitive advisories, but current package audit was not rerun in Stage 3. Pin, review and validate actual production dependencies and images before release.

## Stage 3A proposed ECS read-only audit command list (historical plan)

This is the earlier Stage 3A plan, not a log of completed checks. Stage 3B executed only the subset recorded above after separate owner authorization; the owner expressly excluded Docker management and `sudo -n` commands. Keep raw metadata private and do not install missing packages.

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

1. Stage 3B read-only authorization and identity check were completed. Obtain separate authorization before any additional ECS inspection, especially Docker/firewall commands, or any server state change. Backup destination and restoration remain unverified.
2. Demonstrate the old Review Server can be restored: identify current package, configuration, SQLite and WAL, media, backup method and an isolated restoration check. An unverified old-service recovery path blocks cutover.
3. Decide target Linux architecture and package/runtime versions; pin compatible CPU PyTorch and data images, measure artifact size, checkpoint hash and model-load/inference peaks. Confirm disk for releases, database, private objects, logs and independent backups.
4. Prepare and review production Gateway/Backend/Worker/Sweeper/data-service units, private TLS routes, Nginx policy, secrets, lifecycle and health checks. These are **not yet implemented** in this worktree.
5. Review the conditional [Stage 4 deployment and rollback plan](stage4_deployment_plan.md). Actual deployment, Review Server stop and domain cutover each require their stated separate approvals. GPU AI Node preservation is a code/protocol property; GPU machine acceptance remains outstanding.
