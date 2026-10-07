#!/usr/bin/env bash
set -euo pipefail

# Prepare an immutable source tree from a GitHub commit. This does not switch
# services, install dependencies, or touch an existing release.
if [[ $# -ne 3 ]]; then
  echo "usage: $0 <repository-url> <40-char-commit> <new-release-directory>" >&2
  exit 2
fi

repo_url=$1
commit=$2
destination=$3
branch=handoff/pre-b-transfer-20260929

if [[ ! $commit =~ ^[0-9a-f]{40}$ ]]; then
  echo "a full lowercase Git commit SHA is required" >&2
  exit 2
fi
if [[ -e $destination || -L $destination ]]; then
  echo "release destination already exists" >&2
  exit 1
fi

parent=$(dirname -- "$destination")
mkdir -p -- "$parent"
staging=$(mktemp -d "${parent}/.epilocate-release.XXXXXXXX")
trap 'rm -rf -- "$staging"' EXIT

git clone --quiet --no-checkout --single-branch --branch "$branch" -- "$repo_url" "$staging/repository"
git -C "$staging/repository" cat-file -e "${commit}^{commit}"
if ! git -C "$staging/repository" merge-base --is-ancestor "$commit" "refs/remotes/origin/${branch}"; then
  echo "commit is not on the expected GitHub handoff branch" >&2
  exit 1
fi

mkdir -- "$staging/tree"
git -C "$staging/repository" archive --format=tar "$commit" | tar -xf - -C "$staging/tree"
if [[ -e $staging/tree/SOURCE_COMMIT ]]; then
  echo "source tree unexpectedly contains SOURCE_COMMIT" >&2
  exit 1
fi
printf '%s\n' "$commit" >"$staging/tree/SOURCE_COMMIT"
test "$(cat "$staging/tree/SOURCE_COMMIT")" = "$commit"
mv -- "$staging/tree" "$destination"
echo "prepared_source_commit=$commit"
echo "prepared_release_directory=$destination"
