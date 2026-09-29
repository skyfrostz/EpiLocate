#!/usr/bin/env bash
set -euo pipefail

archive="${1:-/tmp/aid-site.tar.gz}"
release="/opt/aid-site/releases/$(date -u +%Y%m%d%H%M%S)"
if [[ ! -f "$archive" ]]; then echo "Archive not found" >&2; exit 1; fi
if ! id -u aid-site >/dev/null 2>&1; then
  useradd --system --home-dir /var/lib/aid-site --shell /usr/sbin/nologin aid-site
fi
install -d -o root -g root -m 0755 /opt/aid-site /opt/aid-site/releases
install -d -o aid-site -g aid-site -m 0700 /var/lib/aid-site
install -d -o root -g root -m 0755 "$release"
tar -xzf "$archive" -C "$release"
find "$release" -type d -exec chmod 0755 {} +
find "$release" -type f -exec chmod 0644 {} +
chmod 0755 "$release/deploy/install.sh"
if [[ ! -x /opt/aid-site/.venv/bin/python ]]; then
  python3 -m venv /opt/aid-site/.venv
fi
/opt/aid-site/.venv/bin/pip install --disable-pip-version-check -r "$release/requirements.txt"
ln -sfn "$release" /opt/aid-site/current
install -o root -g root -m 0644 "$release/deploy/aid-site.service" /etc/systemd/system/aid-site.service
systemctl daemon-reload
systemctl enable aid-site.service
systemctl restart aid-site.service
for attempt in 1 2 3 4 5 6 7 8 9 10; do
  if curl --fail --silent http://127.0.0.1:8766/healthz; then break; fi
  sleep 1
done
systemctl is-active --quiet aid-site.service
curl --fail --silent http://127.0.0.1:8766/healthz >/dev/null
echo ""
echo "Isolated aid-site service ready at 127.0.0.1:8766"
