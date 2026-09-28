#!/usr/bin/env bash
set -euo pipefail

worker_root=${EPILOCATE_GPU_WORKER_ROOT:-/mnt/epilocate-mvp/source}
credential_file=${EPILOCATE_GPU_WORKER_ENV:-/mnt/epilocate-mvp/secrets/worker.env}
python_bin=${EPILOCATE_GPU_PYTHON:-/root/miniconda3/envs/myconda/bin/python3.12}

if [[ ! -d ${worker_root} || ! -x ${python_bin} ]]; then
  echo "GPU Worker source directory or Python executable is unavailable" >&2
  exit 1
fi

if [[ ! -f ${credential_file} || -L ${credential_file} || ! -O ${credential_file} || $(stat -c '%a' "${credential_file}") != 600 ]]; then
  echo "GPU Worker credential file must be a current-owner regular file with mode 0600" >&2
  exit 1
fi

umask 077
mkdir -p /mnt/epilocate-mvp/data /mnt/epilocate-mvp/logs
cd "${worker_root}"
set -a
# shellcheck disable=SC1090
source "${credential_file}"
set +a
export WORKER_DEVICE=CUDA
export WORKER_POLL_SECONDS=${WORKER_POLL_SECONDS:-2}
exec "${python_bin}" -m worker
