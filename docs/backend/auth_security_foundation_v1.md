# EpiLocate P1 Phase 2 Authentication & Security Foundation v1

> 历史安全基础设计。Phase 5 已实现浏览器 Session Gateway；登录、Cookie、CSRF 与错误体见 [Session Gateway Contract](session_gateway_contract_phase5.md)，用户资源与资产行为见 [Backend API Contract](backend_api_contract_phase5.md)。下文关于 Cookie 仍待采用的文字只记录当时状态。

## Authentication architecture

Backend v2 accepts HTTP `Authorization: Bearer <opaque-token>` on user routes. A provisioned token is high entropy, shown once to the operator, and stored only as SHA-256 in `user_credentials`. Each credential has an issued time, mandatory expiry, optional revocation time, and a user reference. An inactive `User` invalidates all of that user's credentials. Invalid, expired, revoked, and missing credentials all return `401 UNAUTHENTICATED` without revealing which condition occurred.

`EPILOCATE_V2_ALLOW_ENV_TOKENS=true` is an explicit local test-only compatibility switch for the pre-Phase-2 hash mapping. It is `false` in `.example.env` and must remain disabled in production. Production credentials are issued and revoked by `backend_v2.scripts.provision_user` and `backend_v2.scripts.revoke_user`; the token file is created with mode `0600`.

No password or token plaintext is stored in PostgreSQL. The Backend does not implement a login page or an OIDC provider. A production edge may authenticate an OIDC session and map its stable `sub` to a provisioned Backend credential, or inject the same bearer on a protected server-side proxy. The browser never receives S3 credentials, Worker credentials, or a server-held user token. Cookie session adoption would require a separate SameSite/CSRF contract.

## Authorization matrix

| Resource/action | Required identity | Server-side check | Unauthorized result |
| --- | --- | --- | --- |
| Case list/create | User | `owner_user_id = current_user.id`; idempotency actor is the same user | `401` or owner-scoped list |
| Case detail/upload | User | Case owner, non-`DELETING`; Patient and Slice compound ownership | `404 CASE_NOT_FOUND` |
| DICOM read | User | Case owner, retained object, SHA-256 integrity | `404` for other owner; `410 INPUT_EXPIRED` after TTL |
| Prediction/Occlusion create | User | Case owner, Slice belongs to Case, active model, retained input | `404`, `410`, or `422` |
| Job/prediction polling | User | `requested_by_user_id = current_user.id` | `404 JOB_NOT_FOUND` / `404 PREDICTION_NOT_FOUND` |
| Result detail/positions | User | Result → Job → Case owner and completed Job | `404 RESULT_NOT_FOUND` |
| Heatmap asset | User | Result owner, asset belongs to Result, retention and integrity checks | `404 ASSET_NOT_FOUND` or `410 ASSET_EXPIRED` |
| Worker register/heartbeat/claim/result | Worker | DB token hash, enabled node, matching `worker_id`, Attempt/lease checks | `401`, `403`, or `409` per Worker protocol |

All owner failures are evaluated before returning object details, so a user cannot distinguish another user's ID from a nonexistent ID. Result descriptions return an authorized Backend asset route; private S3/MinIO object keys and direct storage URLs are not exposed to the browser.

## Worker boundary

Worker credentials are provisioned separately in `worker_nodes` and are never accepted by user dependencies. User credentials are never accepted by Worker dependencies. Existing Worker v1 Register, Heartbeat, Claim, lease, model hash and Result submission semantics remain unchanged. Worker responses receive `Cache-Control: no-store`.

## Storage and retention

The DICOM bucket remains private. Worker input URLs are signed for at most five minutes and checked against the input retention timestamp. Result assets are long-lived by default; an explicit expired `retention_until` returns `410 ASSET_EXPIRED`. User asset reads go through the authorized Backend route, which reads and verifies the private object using server credentials. S3 access key, secret, private object key and signed URL are never placed in the frontend bundle.

## Error semantics

- `401`: missing, malformed, invalid, expired or revoked credential.
- `403`: authenticated Worker disabled or `worker_id` does not match its credential.
- `404`: resource is not visible to the current owner, or asset/result does not belong to the requested chain.
- `410`: owned input or asset existed but its retention window has expired.
- `409`: valid identity but stale lease, idempotency conflict, or result conflict.
