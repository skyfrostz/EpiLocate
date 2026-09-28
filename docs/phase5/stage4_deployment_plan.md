# EpiLocate P1 Phase 5 — conditional Stage 4 deployment and rollback plan

**Status:** design only, 2026-09-28. No ECS audit authorization or deployment authorization has been granted. Every path, port, package choice and capacity setting below is a proposed value subject to the [Stage 3 read-only audit](stage3_ecs_readiness_report.md). Do not run this plan as a script. Stopping the old Review Server and switching `project.xbstu.com` each require separate explicit owner approval, even after ordinary Stage 4 deployment approval.

## 1. Release gates and stop conditions

1. Complete authorized ECS read-only audit and record actual OS/architecture, CPU, RAM/swap, disk/filesystems, existing workload, Docker/Compose/systemd, occupied ports, Nginx/TLS, Review Server state, PostgreSQL/MinIO feasibility and backup destination. If the old release, SQLite, media or configuration cannot be backed up **and restore-tested**, stop before cutover.
2. Obtain owner approval for the concrete release and a separate change window/approval for Review Server stop and public Nginx route switch. Produce versioned release artifact, checksums, dependency/image pins, deployment units and sanitized config diff for review first. Do not merge or push as part of this plan without explicit approval.
3. Establish server capacity with a one-Worker real CPU rehearsal on synthetic or compliant de-identified DICOM before public cutover. Measure model-load and task peak RSS, CPU, swap, disk I/O, Prediction/Occlusion duration, heartbeat and queue. If the new stack plus old Review Server cannot coexist safely during staging, stop and present a separate-host or revised window option. Do not use the local M5 Pro timing as an ECS estimate.
4. Verify the frozen checkpoint SHA-256 `548b39b9a799a4cbf56982c569d752c2e37ce4ac005089b0339a6194a3cad734` after transfer, with matching `MODEL_HASH`/`MODEL_VERSION`; install compatible Linux CPU PyTorch and other frozen dependencies from reviewed pins. Keep source, checkpoint, training inputs and Worker protocol unchanged. `CUDA`/`AUTO` remain available for a future separate GPU AI Node.
5. Confirm backup space and a restore rehearsal, trusted public TLS, private TLS and MinIO SigV4 routing, private data ports, secret file permissions, safe logging, health probes, database migrations, and release acceptance criteria. Any missing item is a release blocker, not a waived check.

## 2. Target topology and route ownership

```text
Browser ── HTTPS project.xbstu.com:443 ── Nginx
                                         ├─ / and static assets → immutable Vue build
                                         ├─ /auth/* → Session Gateway (loopback HTTP)
                                         └─ /api/v2/{cases,predictions,jobs,results}* → Gateway
Gateway ── loopback HTTP ── FastAPI Backend v2 ── private PostgreSQL + MinIO
CPU Worker ── loopback HTTPS worker edge ── Backend /api/v2/workers/*
CPU Worker ── loopback HTTPS object edge ── private MinIO signed input GET
Sweeper ── private PostgreSQL/MinIO via Backend configuration
```

The public browser Nginx site must deny `/api/v2/workers/*` and Backend `/docs`, `/redoc`, `/openapi.json`; it must never proxy arbitrary `/api/v2/*` directly to Backend. Only the listed user API families go to Gateway. An unknown API path returns 404. Serve SPA fallback only for intended frontend routes; do not let it mask API/auth 404s. Public Nginx should preserve `Host`, forward `X-Forwarded-Proto=https`, enforce upload limits compatible with the Gateway's 21 MiB request cap, apply an additional login rate limit, and avoid query strings in access/error logs. Retain appropriate CSP, no-sniff, frame, referrer and cache policies; ensure service-worker/static caching never caches private API responses. Confirm the actual old site's TLS and ACME routing before changing it.

The proposed on-host private Worker edge is a distinct Nginx listener on `127.0.0.1:9443` that proxies only `/api/v2/workers/*` to loopback Backend; all other routes 404. Its certificate must have a SAN matching the name/IP in `BACKEND_URL=https://127.0.0.1:9443`; the Worker trusts its private CA through `WORKER_CA_CERT`. The proposed private object edge is `127.0.0.1:9444`, proxies the S3 path and **unchanged query** to loopback MinIO, and uses a SAN-matching trusted certificate. Set Backend `EPILOCATE_V2_S3_PUBLIC_ENDPOINT=https://127.0.0.1:9444` (path addressing), while `EPILOCATE_V2_S3_ENDPOINT` stays a private service URL. Preserve the signed `Host` including port (`$http_host`) and request URI in the object proxy; test an actual signed download before accepting it. Deny off-host access by bind/firewall and do not publish S3 credentials. The Worker does not bypass certificate checks. If Nginx cannot support these private listeners without interfering with the existing site, design an equivalent private TLS edge and re-review it before implementation. A future remote GPU AI Node would need its own approved secure Worker/S3 transport; the shared protocol and code remain intact.

Proposed unoccupied application loopback ports: Backend `8890`, Gateway `8891`, Worker TLS `9443`, object TLS `9444`, MinIO API `9000`, PostgreSQL `5432`. **All require ECS occupancy verification**. PostgreSQL and MinIO bind only loopback or an isolated container network. No database, MinIO console, Backend, Gateway or Worker management port is exposed on the public interface.

## 3. Layout, identity and configuration

| Purpose | Proposed location and permissions |
| --- | --- |
| Immutable app releases | `/opt/epilocate/releases/<sha>/` owned by deployment operator, read-only to app users; `/opt/epilocate/current` symlink changed only during approved release. Vue `dist` served from this release. Keep previous release for rollback. |
| Python runtimes | Separate versioned Linux virtualenv(s) under `/opt/epilocate/runtimes/<sha>/`; review and pin CPU Torch/wheels for actual architecture. Never copy macOS `.venv` or unpinned local Compose image into production. |
| Frozen model | `/opt/epilocate/frozen/FORMAL-BL-R18-V1/` with only required checkpoint, protocol and config files, owned by deploy operator, read-only to Worker. Verify hashes before each release. No clinical/research raw data in the package. |
| Runtime state | `/var/lib/epilocate/gateway/sessions.sqlite3`, `/var/lib/epilocate/worker/`, and data volumes for PostgreSQL and MinIO; separate from old Review Server under `/var/lib/epilocate-review`. Ownership: dedicated least-privilege `epilocate-gateway`, `epilocate-backend`, `epilocate-worker`, `epilocate-data` as feasible; 0700 private directories. |
| Secrets and configuration | `/etc/epilocate/{gateway,backend,worker,data}.env` and account/token/key files in private subdirectories, owner/group restricted and 0600 files. Gateway can read only its account/token/session-key files. Worker can read only its provisioned token and private CA. No secret in repo, Vue bundle, URL, shell history, unit text, journal or report. |
| Backups and logs | Separate mounted backup destination or off-host encrypted store after audit; versioned backup manifests/checksums. Journald plus log rotation/retention sized against measured disk; access logs omit query strings. Keep old Review logs and data intact. |

The current local Compose file is not a production manifest. After ECS audit, select pinned PostgreSQL 16 and MinIO image digests compatible with the actual architecture, bind volumes explicitly, set non-placeholder secrets, private networking, restart and health policies, verified bucket-private policy and seven-day `input/` lifecycle. A systemd-managed data-stack unit may supervise a reviewed Compose manifest; Backend, Gateway, one Sweeper and one CPU Worker get separate hardened systemd units with explicit `After`/`Requires` and restart/backoff. Do not make the FastAPI request process run the model. Limit initial Worker concurrency to its existing single-attempt loop; set CPU and memory protection only after measured peaks, with enough headroom for Postgres, MinIO, Nginx and the old Review Server during staging.

Backup format must be decided against the audited target: a consistent PostgreSQL logical dump (`pg_dump` for the selected database) or tested physical snapshot, a point-in-time-consistent MinIO object copy/snapshot with bucket policy and lifecycle metadata, private Gateway account/session/key and Backend credential/lease-secret files, plus release manifests. Keep encryption material and restoration instructions in the restricted backup store; without matching secrets and objects, a database dump alone cannot restore user sessions or result assets. Record backup time, file hashes, sizes, owner permissions and an isolated restore test. Never put raw backups or credentials in Git or the report.

Gateway config uses `EPILOCATE_GATEWAY_PUBLIC_ORIGIN=https://project.xbstu.com` and `EPILOCATE_GATEWAY_BACKEND_ORIGIN=http://127.0.0.1:8890`, plus private account, session DB and key paths. Build Vue with `VITE_API_BASE_URL=/api/v2`. Backend uses PostgreSQL DSN, private S3 endpoint/credentials, private signed-URL endpoint, a random lease secret and `EPILOCATE_V2_ALLOW_ENV_TOKENS=false`. Worker provisioning generates a private 0600 env with the loopback HTTPS Backend origin and frozen hash; the unit invokes `deploy/run_server_cpu_worker.sh <private-env> <linux-python>` and passes `WORKER_CA_CERT` as needed. Run one independent Sweeper process. Generate Gateway accounts and Backend user/Worker credentials using the existing management/provisioning commands after migration, with interactive secret handling and no test credentials in production.

## 4. Health, logs and security acceptance

- Before deployment approval, provide explicit non-sensitive liveness/readiness probes or documented private checks for Backend, Gateway, PostgreSQL, MinIO, Worker registration/heartbeat and Sweeper run. The current Backend/Gateway lack dedicated health endpoints; a process being active alone is insufficient. Any small probe code/config addition needs separate review and tests before release. Never expose diagnostic endpoints with secrets or internal state to public users.
- Capture systemd active/restart status, bounded CPU/RSS, disk and swap, Backend/Worker/Sweeper error counts, queue age, lease expiries, object storage availability and Nginx 5xx. Verify logs cannot contain Bearer tokens, session cookies, passwords, private paths with credentials or SigV4 query strings. Test errors return safe messages.
- Check public TLS certificate chain/expiry and renewal route; use the production trusted chain for browsers and the explicitly trusted private CA for Worker. Keep `Secure; HttpOnly; SameSite=Strict` cookies, CSRF and Origin enforcement, login throttling, logout/expiry/revocation and Backend ownership checks. Inspect effective Nginx configuration for route precedence and public denial of Backend docs/Worker API.
- Validate `input/` retention against `DICOM_RETENTION_DAYS`, MinIO private bucket policy and encryption choice. Preserve database and object backup consistency and test recovery; do not count copies without restoration as backups.

## 5. Sequenced execution — requires later approvals

**Preparatory staging, after ECS audit and ordinary deployment approval; no public route switch:**

1. Record a deployment change ticket with approved artifact SHA, data schema revision, actual ports/paths, resource budget, exact Nginx diff, responsible operator, maintenance window and rollback threshold. Verify old Review Server is healthy and its live service/package/SQLite/WAL/media/config inventory. Copy approved old package/config metadata and make a consistent SQLite online snapshot using the old app's `manage.py snapshot-db` after authorization; back up media and release content. Record checksums, permissions and a private backup manifest. Restore the old snapshot and media into an isolated location and exercise its health/login without touching production. If this fails, stop.
2. Stage a fresh new release directory and reviewed Linux runtimes, private frozen files and checksums, pinned data images/manifests, unit files and secrets. Do not overwrite `/opt/epilocate-review`, `/var/lib/epilocate-review`, the old Nginx site or old SQLite. Establish backup destination and retention for new PostgreSQL, MinIO, Gateway sessions/accounts and release configuration; test a new-stack restore in isolation.
3. Start private PostgreSQL and MinIO, verify health, private binding, bucket policy, object read/write/delete and lifecycle. Take a pre-migration database backup if upgrading a preexisting new-stack DB; record schema revision. Run `alembic -c backend_v2/alembic.ini upgrade head` once as an explicit migration step, then `backend_v2.scripts.validate_migrations` and verify the expected 14 tables. These commands write database state and are **Stage 4 only**. Keep old Review SQLite separate.
4. Provision Backend user credentials, Gateway session key/accounts and CPU Worker credentials with existing commands; verify 0600 secret files and expected revocation procedure without printing values. Start Backend, Gateway, Sweeper and one CPU Worker as distinct supervised processes, in that order; verify model hash, actual CPU register, idle heartbeat, lease and no restart loop. Stage Vue static assets. Validate private Worker HTTPS and signed MinIO URL through the proposed TLS edges; test `WORKER_CA_CERT` without disabled verification.
5. Run an isolated pre-cutover browser/HTTP rehearsal using a separately approved local-only test hostname/origin and matching Gateway public-origin configuration, or a controlled hosts-file mapping and trusted production certificate if feasible. Do not use the public domain's live traffic path or relax `Secure` cookie. Check all Stage 4 acceptance items below. If existing Review Server and new stack cannot coexist within measured capacity, stop and seek a new plan rather than preemptively stopping old service.

**Cutover, only with distinct owner approval for old-service stop and `project.xbstu.com` switch:**

6. Freeze old Review writes at the approved time, take a final consistent SQLite snapshot and media/config backup, verify the backup manifest and isolated restore, then stop the old Review service. Save the exact current Nginx config and release pointer. Install the reviewed EpiLocate site config atomically, run `nginx -t`, and reload Nginx. DNS need not change if the existing domain remains on the same ECS; verify actual DNS/TLS in the authorized change window. Confirm only 80/443 public exposure and that old service remains recoverable offline.
7. Run production-domain acceptance with two new independent team test accounts and a synthetic or compliant de-identified DICOM. Monitor resource and 5xx/queue/lease metrics throughout. Keep an explicit rollback decision deadline and operator available. Do not claim GPU acceptance.

**Normal stop order for the new stack:** stop accepting new browser writes, stop Worker claims/Worker, then Sweeper and Gateway/Backend; stop MinIO/PostgreSQL only after consistent backups and when no dependent process remains. Start in reverse dependency order: data services, migration/checks, Backend, Gateway, Sweeper, Worker, public route. An emergency rollback prioritizes returning the old public route and does not delete new-stack data.

## 6. Rollback trigger and executable restoration order

Trigger rollback if trusted TLS/login is broken, public route exposes Backend/Worker/storage, cross-user authorization fails, a real CPU Prediction/Occlusion or nine-asset check fails, the Worker loops/loses leases, Nginx 5xx is sustained, or measured CPU/RAM/disk exceeds the approved safety budget. The change ticket must set the concrete observation window and thresholds after ECS measurements; unknown thresholds block cutover.

1. Disable new writes by restoring the saved previous Nginx site file or symlink using an atomic replacement; run `nginx -t`, reload Nginx, and confirm the old upstream loopback port from the audit. Do not delete the new database or MinIO objects.
2. Start the preserved old Review Server unit (if it was stopped), restore its previous release pointer and config only if they were changed, and verify old `/healthz`, login and a non-sensitive sample read through `https://project.xbstu.com`. If the live old SQLite or media was damaged, stop the unit, restore the tested online snapshot and matching media/config from the private backup, check integrity in isolation, then start and verify. Do not copy only a possibly live SQLite `.db` without its WAL/online snapshot.
3. Stop or isolate new Worker/Gateway/Backend/Sweeper only after old entry is serving; preserve new PostgreSQL/MinIO, logs and backup for diagnosis. Revoke temporary test credentials as appropriate, record failure timeline and actual rollback verification. Resume the old Review service only after its data and route are confirmed. A failed `nginx -t`, missing backup or failed old restore blocks the cutover before step 6, rather than inviting an improvised rollback.

The commands above are described as operations, not executed here. The responsible operator will substitute audited paths/unit names, record exact command/output in the Stage 4 change ticket, and obtain the separate approvals before any state-changing command.

After the audit resolves the real site file and unit names, the operator can finalize this rollback skeleton; `SAVED_SITE` must be a separately preserved copy from before cutover, `ACTIVE_SITE` the audited live path, and `OLD_UNIT` the audited Review Server service. These are **Stage 4 commands only**, never Stage 3 audit commands:

```sh
install -m 0644 "$SAVED_SITE" "$ACTIVE_SITE"
nginx -t
systemctl reload nginx
systemctl start "$OLD_UNIT"
systemctl is-active "$OLD_UNIT"
curl --fail --silent --show-error https://project.xbstu.com/healthz
```

The site file restore and reload must be executed in a controlled change window with error checks between commands; if `nginx -t` fails, do not reload and use the preserved config to repair the candidate. An exact old-app login/read check and backup restoration command depend on the audited runtime, so fill them in and rehearse them before approval. A domain-route rollback never rolls back the new PostgreSQL schema blindly; preserve new-state backups and resolve schema/data separately.

## 7. Server acceptance matrix

| Evidence to capture on actual ECS | Required outcome |
| --- | --- |
| OS/CPU/RAM/disk and process metrics | Sustained headroom for Nginx, data stack, Gateway, Backend, Sweeper and one CPU Worker; measured peak RSS and task duration; no OOM/swap thrash. |
| Runtime provenance | Linux CPU device recorded, frozen checkpoint file hash matches, no Mock/core-AI stub; CUDA/AUTO code retained but GPU hardware result marked untested. |
| Browser on trusted `https://project.xbstu.com` | Two independent accounts: login, Dashboard, Case create, synthetic/de-identified DICOM upload, Prediction, Occlusion, CT, overlay/layers/opacity, refresh recovery, logout. Record browser, time, screenshots and sanitized job IDs. |
| Real task and data | Prediction and Occlusion `COMPLETED`, `LIVE_CASE`, nine heatmap assets, 16/32/64 px counts 729/169/36, PostgreSQL Result/Asset rows and MinIO bytes/hash reread, Backend API asset reread. |
| Security | A↔B Case/Result/Asset isolation, anonymous denial, cookie/CSRF/Origin/rate/expiry/revocation, no browser Bearer, denied public Worker/docs/storage, private bucket, safe logs and errors. |
| Recovery and coexistence | Worker stop/restart, queued task, lease expiry/retry, persisted result, backup restore and old Review Server rollback drill, measured queue behavior with two users. |
| Checks | Gateway/Backend/Worker/Frontend regression suites, Frontend production build, migration validation, `git diff --check`, production Nginx syntax, service health and trusted TLS. Record passed/skipped/failed/unrun separately. |

Stage 4 must end with a report containing actual ECS measurements, deployment commit and artifact hashes, executed commands, data/backup verification, CPU inference and browser evidence, failure/rollback outcome, unresolved risks and a separate release decision. The Stage 2 self-signed local browser evidence cannot satisfy this server matrix.
