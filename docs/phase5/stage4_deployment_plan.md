# EpiLocate P1 Phase 5 — conditional Stage 4 deployment and rollback plan

**Status:** revised design after the separately authorized 2026-09-28 Stage 3B read-only ECS audit; **neither Stage 4A nor Stage 4B has been approved**. The [Stage 3 report](stage3_ecs_readiness_report.md) distinguishes observed values from unverified dependencies. Do not run this plan as a script. Stage 4A is private deployment and real ECS CPU rehearsal; Stage 4B is a later, independently approved public cutover. Approval of 4A never authorizes stopping the old Review Server or switching `project.xbstu.com`.

| Stage 3B verified constraint | Deployment consequence |
| --- | --- |
| Ubuntu 24.04.4 `x86_64`, KVM, 2 exposed logical vCPUs; 3.5 GiB RAM, about 2.7 GiB available and 4 GiB unused swap at audit time. | Linux CPU wheel compatibility is plausible but untested. Coexistence and model peak are unknown; treat memory and CPU as a Stage 4A safety gate, not as approved capacity. |
| Root ext4 filesystem about 49 GiB, 39 GiB free; no distinct data/backup mount observed. | Stage releases and an old-service copy fit by size alone, but require an independent backup target and actual restore test. Do not rely on same-disk copies for recovery. |
| Review Server active via `epilocate-review.service`, current symlink under `/opt/epilocate-review/releases/`, private SQLite at `/var/lib/epilocate-review/review.sqlite3`, media bundle about 457 MiB; no WAL file at the audit instant. | Preserve old paths and service; take a consistent online snapshot and rehearse isolated restore only after Stage 4A approval. WAL absence is not proof a raw file copy is safe. |
| Nginx 1.24.0 has two enabled HTTPS sites; target domain currently proxies to old loopback 8765, another Aid site proxies to 8766. Current certificate is valid until 2026-12-23 and certbot timer exists. | Do not modify the other site. Public site switch belongs solely to 4B; old site's 64k upload cap cannot serve DICOM and needs a reviewed 4B route change. |
| Candidate 8890/8891/9443/9444/5432/9000 were not listening at one check. | Recheck immediately before Stage 4A binding. This does not reserve ports or establish firewall/cloud security-group policy. |
| Docker/Compose interface and firewall commands were prohibited in Stage 3B. | Versions, images, effective firewall and cloud security group remain unverified. Resolve through separate read-only approval/evidence before committing to the data-service runtime. |

## 1. Release gates and stop conditions

1. The bounded Stage 3B read-only audit is complete. Resolve its remaining evidence gaps: Docker/Compose or alternate runtime, host/cloud firewall, independent backup target, old-service isolated restore method, and approved Linux package/image pins. If the old release, SQLite, media or configuration cannot be backed up **and restore-tested**, stop before any public cutover.
2. Obtain a **separate Stage 4A approval** for a concrete private release, versioned artifact/checksums, process/data units, private TLS and backup rehearsal. Later request a **new Stage 4B approval** for the public Nginx route, Review stop and change window. Do not merge or push without explicit approval.
3. Establish server capacity with one real ECS CPU Worker on synthetic or compliant de-identified DICOM during Stage 4A. Measure model-load and task peak RSS, CPU, swap, disk I/O, Prediction/Occlusion duration, heartbeat and queue while the old services run. If safe coexistence fails, stop and present a separate compute host, larger instance or revised deployment topology. Do not use local M5 Pro timing as an ECS estimate.
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

Proposed application loopback ports: Backend `8890`, Gateway `8891`, Worker TLS `9443`, object TLS `9444`, MinIO API `9000`, PostgreSQL `5432`. None was listening during the Stage 3B instant check; recheck occupancy before binding and verify actual data-service topology after the separately approved runtime audit. PostgreSQL and MinIO bind only loopback or an isolated container network. No database, MinIO console, Backend, Gateway or Worker management port is exposed on the public interface.

## 3. Layout, identity and configuration

| Purpose | Proposed location and permissions |
| --- | --- |
| Immutable app releases | `/opt/epilocate/releases/<sha>/` owned by deployment operator, read-only to app users; `/opt/epilocate/current` symlink changed only during approved release. Vue `dist` served from this release. Keep previous release for rollback. |
| Python runtimes | Separate versioned Linux virtualenv(s) under `/opt/epilocate/runtimes/<sha>/`; review and pin CPU Torch/wheels for actual architecture. Never copy macOS `.venv` or unpinned local Compose image into production. |
| Frozen model | `/opt/epilocate/frozen/FORMAL-BL-R18-V1/` with only required checkpoint, protocol and config files, owned by deploy operator, read-only to Worker. Verify hashes before each release. No clinical/research raw data in the package. |
| Runtime state | `/var/lib/epilocate/gateway/sessions.sqlite3`, `/var/lib/epilocate/worker/`, and data volumes for PostgreSQL and MinIO; separate from old Review Server under `/var/lib/epilocate-review`. Ownership: dedicated least-privilege `epilocate-gateway`, `epilocate-backend`, `epilocate-worker`, `epilocate-data` as feasible; 0700 private directories. |
| Secrets and configuration | `/etc/epilocate/{gateway,backend,worker,data}.env` and account/token/key files in private subdirectories, owner/group restricted and 0600 files. Gateway can read only its account/token/session-key files. Worker can read only its provisioned token and private CA. No secret in repo, Vue bundle, URL, shell history, unit text, journal or report. |
| Backups and logs | Stage 3B found no separate backup mount: provide a separately approved off-host or independent-volume encrypted destination, with versioned backup manifests/checksums and a restore test. Journald plus log rotation/retention sized against measured disk; access logs omit query strings. Keep old Review logs and data intact. |

The current local Compose file is not a production manifest. After ECS audit, select pinned PostgreSQL 16 and MinIO image digests compatible with the actual architecture, bind volumes explicitly, set non-placeholder secrets, private networking, restart and health policies, verified bucket-private policy and seven-day `input/` lifecycle. A systemd-managed data-stack unit may supervise a reviewed Compose manifest; Backend, Gateway, one Sweeper and one CPU Worker get separate hardened systemd units with explicit `After`/`Requires` and restart/backoff. Do not make the FastAPI request process run the model. Limit initial Worker concurrency to its existing single-attempt loop; set CPU and memory protection only after measured peaks, with enough headroom for Postgres, MinIO, Nginx and the old Review Server during staging.

Backup format must be decided against the audited target: a consistent PostgreSQL logical dump (`pg_dump` for the selected database) or tested physical snapshot, a point-in-time-consistent MinIO object copy/snapshot with bucket policy and lifecycle metadata, private Gateway account/session/key and Backend credential/lease-secret files, plus release manifests. Keep encryption material and restoration instructions in the restricted backup store; without matching secrets and objects, a database dump alone cannot restore user sessions or result assets. Record backup time, file hashes, sizes, owner permissions and an isolated restore test. Never put raw backups or credentials in Git or the report.

Gateway config uses `EPILOCATE_GATEWAY_PUBLIC_ORIGIN=https://project.xbstu.com` and `EPILOCATE_GATEWAY_BACKEND_ORIGIN=http://127.0.0.1:8890`, plus private account, session DB and key paths. Build Vue with `VITE_API_BASE_URL=/api/v2`. Backend uses PostgreSQL DSN, private S3 endpoint/credentials, private signed-URL endpoint, a random lease secret and `EPILOCATE_V2_ALLOW_ENV_TOKENS=false`. Worker provisioning generates a private 0600 env with the loopback HTTPS Backend origin and frozen hash; the unit invokes `deploy/run_server_cpu_worker.sh <private-env> <linux-python>` and passes `WORKER_CA_CERT` as needed. Run one independent Sweeper process. Generate Gateway accounts and Backend user/Worker credentials using the existing management/provisioning commands after migration, with interactive secret handling and no test credentials in production.

## 4. Health, logs and security acceptance

- Before deployment approval, provide explicit non-sensitive liveness/readiness probes or documented private checks for Backend, Gateway, PostgreSQL, MinIO, Worker registration/heartbeat and Sweeper run. The current Backend/Gateway lack dedicated health endpoints; a process being active alone is insufficient. Any small probe code/config addition needs separate review and tests before release. Never expose diagnostic endpoints with secrets or internal state to public users.
- Capture systemd active/restart status, bounded CPU/RSS, disk and swap, Backend/Worker/Sweeper error counts, queue age, lease expiries, object storage availability and Nginx 5xx. Verify logs cannot contain Bearer tokens, session cookies, passwords, private paths with credentials or SigV4 query strings. Test errors return safe messages.
- Check public TLS certificate chain/expiry and renewal route; use the production trusted chain for browsers and the explicitly trusted private CA for Worker. Keep `Secure; HttpOnly; SameSite=Strict` cookies, CSRF and Origin enforcement, login throttling, logout/expiry/revocation and Backend ownership checks. Inspect effective Nginx configuration for route precedence and public denial of Backend docs/Worker API.
- Validate `input/` retention against `DICOM_RETENTION_DAYS`, MinIO private bucket policy and encryption choice. Preserve database and object backup consistency and test recovery; do not count copies without restoration as backups.

## 5. Sequenced execution — requires later approvals

**Stage 4A — private deployment and CPU rehearsal, only after its separate approval; no public route switch:**

1. Record a deployment change ticket with approved artifact SHA, data schema revision, actual ports/paths, resource budget, exact Nginx diff, responsible operator, maintenance window and rollback threshold. Verify old Review Server is healthy and its live service/package/SQLite/WAL/media/config inventory. Copy approved old package/config metadata and make a consistent SQLite online snapshot using the old app's `manage.py snapshot-db` after authorization; back up media and release content. Record checksums, permissions and a private backup manifest. Restore the old snapshot and media into an isolated location and exercise its health/login without touching production. If this fails, stop.
2. Stage a fresh new release directory and reviewed Linux runtimes, private frozen files and checksums, pinned data images/manifests, unit files and secrets. Do not overwrite `/opt/epilocate-review`, `/var/lib/epilocate-review`, the old Nginx site or old SQLite. Establish backup destination and retention for new PostgreSQL, MinIO, Gateway sessions/accounts and release configuration; test a new-stack restore in isolation.
3. Start private PostgreSQL and MinIO, verify health, private binding, bucket policy, object read/write/delete and lifecycle. Take a pre-migration database backup if upgrading a preexisting new-stack DB; record schema revision. Run `alembic -c backend_v2/alembic.ini upgrade head` once as an explicit migration step, then `backend_v2.scripts.validate_migrations` and verify the expected 14 tables. These commands write database state and are **Stage 4 only**. Keep old Review SQLite separate.
4. Provision Backend user credentials, Gateway session key/accounts and CPU Worker credentials with existing commands; verify 0600 secret files and expected revocation procedure without printing values. Start Backend, Gateway, Sweeper and one CPU Worker as distinct supervised processes, in that order; verify model hash, actual CPU register, idle heartbeat, lease and no restart loop. Stage Vue static assets. Validate private Worker HTTPS and signed MinIO URL through the proposed TLS edges; test `WORKER_CA_CERT` without disabled verification.
5. Run a private browser rehearsal with an approved test hostname/origin, matching Gateway public-origin configuration and a certificate/CA trusted by that test browser; use a restricted tunnel or network path only if explicitly authorized for Stage 4A. Keep the existing public domain on Review Server and retain `Secure` cookies. Use two independent accounts and synthetic/de-identified DICOM for real CPU Prediction, three-scale Occlusion, CT/overlay/refresh, ownership and storage checks. Measure peak memory/CPU, queue and lease behavior. If the old Review Server and new stack cannot coexist within an agreed safety budget, stop and seek a new plan rather than stopping old service.

Stage 4A passes only after actual Linux CPU `LIVE_CASE` evidence (Prediction/Occlusion `COMPLETED`, nine assets, 729/169/36 positions), PostgreSQL/MinIO reread and hash verification, private HTTPS and SigV4 checks, two-user authorization, a tested old-system backup/isolated restore, and stable coexistence metrics. Its report must include the exact browser/private origin and server resource peaks. No Stage 4B action follows automatically.

**Stage 4B — production cutover, only after Stage 4A acceptance and distinct owner approval for old-service stop and `project.xbstu.com` switch:**

6. Freeze old Review writes at the approved time, take a final consistent SQLite snapshot and media/config backup, verify the backup manifest and isolated restore, then stop `epilocate-review.service`. Save the exact current `/etc/nginx/sites-enabled/epilocate-review.conf` and release pointer. Change only the reviewed target-domain site config atomically, run `nginx -t`, and reload Nginx; preserve the separate Aid site. DNS need not change if the existing domain remains on the same ECS; verify actual DNS/TLS in the authorized change window. Confirm only approved public paths/ports and that old service remains recoverable offline.
7. Run production-domain acceptance with two new independent team test accounts and a synthetic or compliant de-identified DICOM. Monitor resource and 5xx/queue/lease metrics throughout. Keep an explicit rollback decision deadline and operator available. Do not claim GPU acceptance.

**Normal stop order for the new stack:** stop accepting new browser writes, stop Worker claims/Worker, then Sweeper and Gateway/Backend; stop MinIO/PostgreSQL only after consistent backups and when no dependent process remains. Start in reverse dependency order: data services, migration/checks, Backend, Gateway, Sweeper, Worker, public route. An emergency rollback prioritizes returning the old public route and does not delete new-stack data.

## 6. Rollback trigger and executable restoration order

Trigger rollback if trusted TLS/login is broken, public route exposes Backend/Worker/storage, cross-user authorization fails, a real CPU Prediction/Occlusion or nine-asset check fails, the Worker loops/loses leases, Nginx 5xx is sustained, or measured CPU/RAM/disk exceeds the approved safety budget. The change ticket must set the concrete observation window and thresholds after ECS measurements; unknown thresholds block cutover.

1. Preserve new-stack database, MinIO and logs; stop accepting new writes by the approved maintenance response if available. If old SQLite/media were damaged, restore the **tested** online snapshot and matching media/config while the old unit is stopped, verify integrity in isolation, then proceed. Restore its previous release pointer/config only if changed; start `epilocate-review.service` and verify its private loopback health before changing the public route. Do not copy only a possibly live SQLite `.db` without its WAL/online snapshot.
2. Restore the saved previous `/etc/nginx/sites-enabled/epilocate-review.conf` site file or symlink using an atomic replacement, run `nginx -t`, reload Nginx, and verify old `/healthz`, login and a non-sensitive sample read through `https://project.xbstu.com`. Preserve the separate Aid site. Do not delete new PostgreSQL or MinIO objects.
3. Stop or isolate new Worker/Gateway/Backend/Sweeper only after old entry is serving; preserve new PostgreSQL/MinIO, logs and backup for diagnosis. Revoke temporary test credentials as appropriate, record failure timeline and actual rollback verification. Resume the old Review service only after its data and route are confirmed. A failed `nginx -t`, missing backup or failed old restore blocks the cutover before step 6, rather than inviting an improvised rollback.

The commands above are described as operations, not executed here. The responsible operator will substitute audited paths/unit names, record exact command/output in the Stage 4 change ticket, and obtain the separate approvals before any state-changing command.

The audited old unit is `epilocate-review.service` and target site path is `/etc/nginx/sites-enabled/epilocate-review.conf`. The operator must still choose and rehearse `SAVED_SITE`, a separately preserved pre-cutover copy, and fill in an isolated restore command. These are **Stage 4B commands only**, never Stage 3 audit commands:

```sh
systemctl start epilocate-review.service
systemctl is-active epilocate-review.service
curl --fail --silent --show-error -H 'Host: project.xbstu.com' http://127.0.0.1:8765/healthz
install -m 0644 "$SAVED_SITE" /etc/nginx/sites-enabled/.epilocate-review.conf.rollback
mv -f /etc/nginx/sites-enabled/.epilocate-review.conf.rollback /etc/nginx/sites-enabled/epilocate-review.conf
nginx -t
systemctl reload nginx
curl --fail --silent --show-error https://project.xbstu.com/healthz
```

The site file restore and reload must be executed in a controlled change window with error checks between commands; if `nginx -t` fails, do not reload and use the preserved config to repair the candidate. An exact old-app login/read check and backup restoration command depend on the audited runtime, so fill them in and rehearse them before approval. A domain-route rollback never rolls back the new PostgreSQL schema blindly; preserve new-state backups and resolve schema/data separately.

## 7. Stage 4B production acceptance matrix

| Evidence to capture on actual ECS | Required outcome |
| --- | --- |
| OS/CPU/RAM/disk and process metrics | Sustained headroom for Nginx, data stack, Gateway, Backend, Sweeper and one CPU Worker; measured peak RSS and task duration; no OOM/swap thrash. |
| Runtime provenance | Linux CPU device recorded, frozen checkpoint file hash matches, no Mock/core-AI stub; CUDA/AUTO code retained but GPU hardware result marked untested. |
| Browser on trusted `https://project.xbstu.com` | Two independent accounts: login, Dashboard, Case create, synthetic/de-identified DICOM upload, Prediction, Occlusion, CT, overlay/layers/opacity, refresh recovery, logout. Record browser, time, screenshots and sanitized job IDs. |
| Real task and data | Prediction and Occlusion `COMPLETED`, `LIVE_CASE`, nine heatmap assets, 16/32/64 px counts 729/169/36, PostgreSQL Result/Asset rows and MinIO bytes/hash reread, Backend API asset reread. |
| Security | A↔B Case/Result/Asset isolation, anonymous denial, cookie/CSRF/Origin/rate/expiry/revocation, no browser Bearer, denied public Worker/docs/storage, private bucket, safe logs and errors. |
| Recovery and coexistence | Worker stop/restart, queued task, lease expiry/retry, persisted result, backup restore and old Review Server rollback drill, measured queue behavior with two users. |
| Checks | Gateway/Backend/Worker/Frontend regression suites, Frontend production build, migration validation, `git diff --check`, production Nginx syntax, service health and trusted TLS. Record passed/skipped/failed/unrun separately. |

Stage 4A must produce a private rehearsal report with actual ECS peaks, frozen hash, data/asset verification, old-system backup and isolated restore, and an explicit pass/fail coexistence decision. Stage 4B needs its own approval and later report covering production-domain HTTPS, route/security checks, real CPU browser E2E, change-window measurements and the rehearsed rollback outcome. The Stage 2 self-signed local browser evidence cannot satisfy either server acceptance gate.
