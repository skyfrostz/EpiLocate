# EpiLocate browser session gateway — Phase 5

**现行浏览器接口与错误体：** [Session Gateway Contract](../docs/backend/session_gateway_contract_phase5.md)。此 README 主要保留账户与秘密文件的运维说明。

The gateway is the browser entry for existing Backend v2 **user** APIs. Backend v2 remains the source of user identity, revocable Bearer credentials, Case ownership, and asset authorization. This package adds personal password login and revocable browser sessions. It does not expose Worker routes, execute inference, or change the frozen Worker/API protocol.

## Account and secret lifecycle

1. Migrate Backend v2 and use `python -m backend_v2.scripts.provision_user --auth-subject <opaque-member-id> --expires-in-days 30 --output /secure/member.env` for **each** member. This command writes one Backend user token to a mode `0600` file. The gateway does not sign or issue Backend tokens.
2. Run `python -m session_gateway.manage create-key --output /secure/gateway.key` once; keep this mode `0600` key outside Git and backed up in the server secret store.
3. Run `python -m session_gateway.manage set-account --accounts /secure/accounts.json --sessions /private/sessions.sqlite3 --username <member> --token-file /secure/member.env`. Password input is interactive and stored only as an Argon2id hash. The account file is mode `0600`. Updating an account revokes that member's previous sessions.
4. Revoke browser sessions with `python -m session_gateway.manage revoke-sessions --sessions /private/sessions.sqlite3 --username <member>`. To stop future login, use `disable-account` with the same `--accounts`, `--sessions`, and `--username` arguments. Backend tokens can additionally be revoked with the existing `backend_v2.scripts.revoke_user` command; the gateway then receives Backend 401 and the browser returns to login.

The account file contains password hashes and absolute paths to Backend token files, not plaintext tokens. The gateway reads each token file server-side without executing shell text. Accounts, token files, session key, session database, and parent directories must be private and outside the static Frontend root. Never serve these paths through Nginx or copy them into the Frontend build.

## Runtime contract

Set these process environment variables:

```text
EPILOCATE_GATEWAY_PUBLIC_ORIGIN=https://project.xbstu.com
EPILOCATE_GATEWAY_BACKEND_ORIGIN=http://127.0.0.1:8890
EPILOCATE_GATEWAY_ACCOUNTS_FILE=/secure/accounts.json
EPILOCATE_GATEWAY_SESSIONS_FILE=/private/sessions.sqlite3
EPILOCATE_GATEWAY_SESSION_KEY_FILE=/secure/gateway.key
```

Run behind a TLS reverse proxy bound to the public origin: `uvicorn session_gateway.app:create_app --factory --host 127.0.0.1 --port <private-port>`. The gateway requires the Backend origin to be loopback HTTP. Nginx must route `/auth/*` and browser `/api/v2/*` to the gateway; it must not expose Backend v2 directly to browsers. Worker traffic uses a separate authenticated Backend route in the current MVP deployment, outside the browser gateway.

`POST /auth/login` requires a same-origin `Origin` header. It verifies the password hash and probes the member's existing Backend credential before issuing an eight-hour, `HttpOnly; Secure; SameSite=Strict` cookie. Failed login attempts are limited by account and source IP. `GET /auth/session` returns the display username and CSRF value. State-changing requests to `/api/v2/*` and `POST /auth/logout` require both the same origin and `X-CSRF-Token`. Logout, expiry, account disable, and administrative revocation invalidate sessions. The gateway strips browser `Authorization` and injects only the mapped user token into its loopback Backend request. Responses never include tokens.

The Frontend is built with `VITE_API_BASE_URL=/api/v2`; its production static files can be served by Nginx. During local development, `API_PROXY_TARGET` points to the gateway, not directly to Backend. The local full browser smoke test requires an HTTPS origin so the Secure cookie and Origin gate are exercised as deployed.

Phase 5 已在 ECS 的独立 `/mvp/` 测试入口部署 Gateway、Backend、PostgreSQL 与 MinIO，并由远端 RTX 3090 CUDA Worker 完成端到端工程验证。该入口不是正式生产环境；ECS CPU Worker 当前未启动，代码仍保留 CPU/CUDA/AUTO 模式。部署事实见 [Phase 5 MVP 报告](../docs/phase5/gpu_full_chain_mvp_report.md)。
