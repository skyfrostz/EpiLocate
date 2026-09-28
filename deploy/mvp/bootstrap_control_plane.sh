#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "bootstrap_control_plane.sh must run as root" >&2
  exit 1
fi

release_root=/opt/epilocate-mvp/current
config_root=/etc/epilocate-mvp
state_root=/var/lib/epilocate-mvp
backend_user=epilocate-backend
gateway_user=epilocate-gateway
minio_user=epilocate-minio
bucket=epilocate-private

if [[ ! -x ${release_root}/.venv/bin/python ]]; then
  echo "release virtual environment is missing" >&2
  exit 1
fi

cd "${release_root}"

for runtime_user in "${backend_user}" "${gateway_user}" "${minio_user}"; do
  if ! id "${runtime_user}" >/dev/null 2>&1; then
    useradd --system --home-dir "${state_root}" --no-create-home --shell /usr/sbin/nologin "${runtime_user}"
  fi
done
install -d -o root -g root -m 0755 "${config_root}" "${state_root}"
install -d -o "${minio_user}" -g "${minio_user}" -m 0700 "${state_root}/minio"
install -d -o "${gateway_user}" -g "${gateway_user}" -m 0700 "${state_root}/gateway" "${state_root}/secrets"

umask 077
if [[ ! -f ${config_root}/minio.env ]]; then
  minio_password=$(openssl rand -hex 32)
  temporary=$(mktemp "${config_root}/.minio.env.XXXXXX")
  {
    printf 'MINIO_ROOT_USER=epilocate_mvp\n'
    printf 'MINIO_ROOT_PASSWORD=%s\n' "${minio_password}"
    printf 'MINIO_BROWSER=off\n'
  } >"${temporary}"
  mv "${temporary}" "${config_root}/minio.env"
fi

if [[ ! -f ${config_root}/backend.env ]]; then
  database_password=$(openssl rand -hex 32)
  lease_secret=$(openssl rand -hex 48)
  temporary=$(mktemp "${config_root}/.backend.env.XXXXXX")
  # shellcheck disable=SC1091
  source "${config_root}/minio.env"
  runuser -u postgres -- psql --quiet --set=ON_ERROR_STOP=1 --set=dbpass="${database_password}" <<'SQL'
SELECT format('CREATE ROLE epilocate_mvp LOGIN PASSWORD %L', :'dbpass')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'epilocate_mvp')\gexec
SELECT format('ALTER ROLE epilocate_mvp PASSWORD %L', :'dbpass')\gexec
SELECT 'CREATE DATABASE epilocate_mvp OWNER epilocate_mvp'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'epilocate_mvp')\gexec
SQL
  {
    printf 'EPILOCATE_V2_DATABASE_URL=postgresql+psycopg://epilocate_mvp:%s@127.0.0.1:5432/epilocate_mvp\n' "${database_password}"
    printf 'EPILOCATE_V2_DB_POOL_SIZE=2\n'
    printf 'EPILOCATE_V2_DB_MAX_OVERFLOW=1\n'
    printf 'EPILOCATE_V2_ALLOW_ENV_TOKENS=false\n'
    printf 'EPILOCATE_V2_LEASE_SECRET=%s\n' "${lease_secret}"
    printf 'EPILOCATE_V2_S3_BUCKET=%s\n' "${bucket}"
    printf 'EPILOCATE_V2_S3_ENDPOINT=http://127.0.0.1:59000\n'
    printf 'EPILOCATE_V2_S3_PUBLIC_ENDPOINT=https://project.xbstu.com\n'
    printf 'EPILOCATE_V2_S3_REGION=us-east-1\n'
    printf 'EPILOCATE_V2_S3_ADDRESSING_STYLE=path\n'
    printf 'EPILOCATE_V2_S3_SERVER_SIDE_ENCRYPTION=false\n'
    printf 'EPILOCATE_V2_S3_ACCESS_KEY=%s\n' "${MINIO_ROOT_USER}"
    printf 'EPILOCATE_V2_S3_SECRET_KEY=%s\n' "${MINIO_ROOT_PASSWORD}"
    printf 'AWS_EC2_METADATA_DISABLED=true\n'
    printf 'DICOM_RETENTION_DAYS=7\n'
  } >"${temporary}"
  mv "${temporary}" "${config_root}/backend.env"
fi

if [[ ! -f ${config_root}/gateway.env ]]; then
  temporary=$(mktemp "${config_root}/.gateway.env.XXXXXX")
  {
    printf 'EPILOCATE_GATEWAY_PUBLIC_ORIGIN=https://project.xbstu.com\n'
    printf 'EPILOCATE_GATEWAY_BACKEND_ORIGIN=http://127.0.0.1:8890\n'
    printf 'EPILOCATE_GATEWAY_ACCOUNTS_FILE=%s/secrets/accounts.json\n' "${state_root}"
    printf 'EPILOCATE_GATEWAY_SESSIONS_FILE=%s/gateway/sessions.sqlite3\n' "${state_root}"
    printf 'EPILOCATE_GATEWAY_SESSION_KEY_FILE=%s/secrets/gateway.key\n' "${state_root}"
  } >"${temporary}"
  mv "${temporary}" "${config_root}/gateway.env"
fi

chmod 0640 "${config_root}"/*.env
chown root:"${minio_user}" "${config_root}/minio.env"
chown root:"${backend_user}" "${config_root}/backend.env"
chown root:"${gateway_user}" "${config_root}/gateway.env"

install -o root -g root -m 0644 "${release_root}/deploy/mvp/epilocate-minio.service" /etc/systemd/system/
install -o root -g root -m 0644 "${release_root}/deploy/mvp/epilocate-backend.service" /etc/systemd/system/
install -o root -g root -m 0644 "${release_root}/deploy/mvp/epilocate-gateway.service" /etc/systemd/system/
install -o root -g root -m 0644 "${release_root}/deploy/mvp/epilocate-sweeper.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now epilocate-minio.service

for _ in {1..30}; do
  if curl --fail --silent --show-error http://127.0.0.1:59000/minio/health/ready >/dev/null; then
    break
  fi
  sleep 1
done
curl --fail --silent --show-error http://127.0.0.1:59000/minio/health/ready >/dev/null

set -a
# shellcheck disable=SC1091
source "${config_root}/backend.env"
set +a
"${release_root}/.venv/bin/python" - <<'PY'
import os
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

bucket = os.environ["EPILOCATE_V2_S3_BUCKET"]
client = boto3.client(
    "s3",
    endpoint_url=os.environ["EPILOCATE_V2_S3_ENDPOINT"],
    region_name=os.environ["EPILOCATE_V2_S3_REGION"],
    aws_access_key_id=os.environ["EPILOCATE_V2_S3_ACCESS_KEY"],
    aws_secret_access_key=os.environ["EPILOCATE_V2_S3_SECRET_KEY"],
    config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
)
try:
    client.head_bucket(Bucket=bucket)
except ClientError:
    client.create_bucket(Bucket=bucket)
client.put_bucket_lifecycle_configuration(Bucket=bucket, LifecycleConfiguration={
    "Rules": [{"ID": "expire-input-after-seven-days", "Status": "Enabled",
               "Filter": {"Prefix": "input/"}, "Expiration": {"Days": 7}}]
})
PY

"${release_root}/.venv/bin/alembic" -c "${release_root}/backend_v2/alembic.ini" upgrade head
"${release_root}/.venv/bin/python" -m backend_v2.scripts.validate_migrations >/dev/null

if [[ ! -f ${state_root}/secrets/gateway.key ]]; then
  runuser -u "${gateway_user}" -- "${release_root}/.venv/bin/python" -m session_gateway.manage \
    create-key --output "${state_root}/secrets/gateway.key" >/dev/null
fi
if [[ ! -f ${state_root}/secrets/accounts.json ]]; then
  install -o "${gateway_user}" -g "${gateway_user}" -m 0600 /dev/null "${state_root}/secrets/accounts.json"
  printf '{}\n' >"${state_root}/secrets/accounts.json"
  chown "${gateway_user}:${gateway_user}" "${state_root}/secrets/accounts.json"
  chmod 0600 "${state_root}/secrets/accounts.json"
fi

systemctl enable --now epilocate-backend.service epilocate-gateway.service epilocate-sweeper.service
echo "control_plane_bootstrap=complete"
