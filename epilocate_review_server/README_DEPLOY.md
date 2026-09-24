# EpiLocate Review Server deployment

This service is limited to the frozen 13-case RICORD manual review. It does not
create a cohort or split and does not start training. Never upload DICOM files,
`data/full_raw`, internal documents, model outputs, credentials, or source paths.

## Runtime layout

```text
/opt/epilocate-review/
  .venv/
  releases/<version>/
  current -> releases/<version>
  review_bundle/
/var/lib/epilocate-review/
  review.sqlite3
  exports/
/etc/epilocate-review/epilocate-review.env
```

The application account owns only `/var/lib/epilocate-review`. Release files and
the review bundle remain root-owned and read-only to the service.

## 1. Build and verify locally

```bash
.venv/bin/python scripts/build_review_bundle.py \
  --output outputs/data/formal_series_rule_b_review_bundle_v1

.venv/bin/python -m pytest -q tests/review_server
git diff --check
```

Before uploading, inspect the package file list. The application whitelist is
`epilocate_review_server/app`, `epilocate_review_server/migrations`,
`epilocate_review_server/templates`, `epilocate_review_server/static`,
`epilocate_review_server/manage.py`, the two pinned requirements files, and
`epilocate_review_server/deploy`. Preserve this package directory under the
release root; `/opt/epilocate-review/current` must therefore contain the
`epilocate_review_server/` directory. The bundle whitelist is `bundle.json`,
PNG assets, and no other file type.

## 2. Prepare the host

```bash
apt-get update
apt-get install --yes python3-venv nginx certbot
adduser --system --group --home /var/lib/epilocate-review \
  --no-create-home epilocate-review
groupadd --system epilocate-review-media || true
usermod --append --groups epilocate-review-media epilocate-review
usermod --append --groups epilocate-review-media www-data
install -d -o root -g root -m 0755 \
  /opt/epilocate-review /opt/epilocate-review/releases
install -d -o root -g epilocate-review-media -m 0750 \
  /opt/epilocate-review/review_bundle
install -d -o epilocate-review -g epilocate-review -m 0750 \
  /var/lib/epilocate-review /var/lib/epilocate-review/exports
install -d -o root -g epilocate-review -m 0750 /etc/epilocate-review
chown -R root:epilocate-review-media /opt/epilocate-review/review_bundle
find /opt/epilocate-review/review_bundle -type d -exec chmod 0750 {} +
find /opt/epilocate-review/review_bundle -type f -exec chmod 0640 {} +
python3 -m venv /opt/epilocate-review/.venv
```

Install exactly the pinned production requirements from the uploaded release:

```bash
/opt/epilocate-review/.venv/bin/pip install \
  --requirement \
  /opt/epilocate-review/current/epilocate_review_server/requirements-server.txt
```

## 3. Configure and initialize

Create `/etc/epilocate-review/epilocate-review.env` as root with mode `0640`,
group `epilocate-review`:

```dotenv
EPILOCATE_ENV=production
EPILOCATE_DATABASE=/var/lib/epilocate-review/review.sqlite3
EPILOCATE_BUNDLE=/opt/epilocate-review/review_bundle/bundle.json
EPILOCATE_ALLOWED_HOSTS=project.xbstu.com
EPILOCATE_ALLOWED_ORIGINS=https://project.xbstu.com
EPILOCATE_SESSION_HOURS=8
EPILOCATE_SECURE_COOKIES=true
EPILOCATE_TRUST_PROXY_HEADERS=true
```

Initialize SQLite and create the three accounts interactively. `create-user`
uses `getpass`; do not pipe or place passwords on the command line.

```bash
sudo -u epilocate-review -g epilocate-review \
  sh -c 'cd /opt/epilocate-review/current && exec /opt/epilocate-review/.venv/bin/python -m epilocate_review_server.manage init-db'
sudo -u epilocate-review -g epilocate-review \
  sh -c 'cd /opt/epilocate-review/current && exec /opt/epilocate-review/.venv/bin/python -m epilocate_review_server.manage create-user admin --role admin'
sudo -u epilocate-review -g epilocate-review \
  sh -c 'cd /opt/epilocate-review/current && exec /opt/epilocate-review/.venv/bin/python -m epilocate_review_server.manage create-user wangmiao --role reviewer'
sudo -u epilocate-review -g epilocate-review \
  sh -c 'cd /opt/epilocate-review/current && exec /opt/epilocate-review/.venv/bin/python -m epilocate_review_server.manage create-user zouxinyu --role reviewer'
```

Install the systemd unit, then verify that Uvicorn only binds loopback:

```bash
install -o root -g root -m 0644 \
  /opt/epilocate-review/current/epilocate_review_server/deploy/epilocate-review.service \
  /etc/systemd/system/epilocate-review.service
systemctl daemon-reload
systemctl enable --now epilocate-review
systemctl status epilocate-review --no-pager
ss -lntp | grep 127.0.0.1:8765
```

## 4. DNS and TLS

Before changing DNS, query the HiChina authoritative nameservers and confirm
that no conflicting record exists. Create only this record:

```text
A  project.xbstu.com  47.120.42.220
```

Ensure the cloud security group permits inbound TCP 80 and 443. This deployment
does not change port 22. Install
`/opt/epilocate-review/current/epilocate_review_server/deploy/nginx-bootstrap.conf`
first, create `/var/www/certbot`, run `nginx -t`, and reload Nginx. After
authoritative DNS resolves to the ECS public IP, request the certificate:

```bash
certbot certonly --webroot -w /var/www/certbot \
  -d project.xbstu.com
```

Replace the bootstrap server block with
`/opt/epilocate-review/current/epilocate_review_server/deploy/nginx.conf`, then:

```bash
nginx -t
systemctl reload nginx
systemctl status certbot.timer --no-pager
certbot renew --dry-run
```

HSTS is deliberately absent in v1. Add it only after a separate operational
decision confirms stable HTTPS and recovery procedures.

## 5. Acceptance and manual recovery artifacts

The health endpoint contains no review data:

```bash
curl --fail https://project.xbstu.com/healthz
```

Verify direct internal media access is denied, production docs are absent, and
port 8765 is not publicly bound. Complete the three-account browser flow before
using real decisions.

Create a manual SQLite snapshot as the application account:

```bash
sudo -u epilocate-review -g epilocate-review \
  /opt/epilocate-review/.venv/bin/python -m epilocate_review_server.manage \
  snapshot-db /var/lib/epilocate-review/exports/review-$(date -u +%Y%m%dT%H%M%SZ).sqlite3
```

Download an admin snapshot CSV at any time. The final CSV is available only
when all 13 cases have final, non-`DEFER` decisions. Validate the downloaded file
inside this repository:

```bash
.venv/bin/python scripts/validate_manual_series_decisions.py path/to/export.csv
```

Exit code `0` is required before asking the project owner for an explicit final
cohort decision. Exit code `2` means unresolved or `DEFER`; exit code `1` means
invalid data. The review service itself never advances that boundary.
