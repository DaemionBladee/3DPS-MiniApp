#!/usr/bin/env bash
# Isolated Cloud/local auth tests; never discovers or connects production data.
set -euo pipefail
export UV_CACHE_DIR="${UV_CACHE_DIR:-${TMPDIR:-/tmp}/3dps-uv-cache}"
export UV_LINK_MODE="${UV_LINK_MODE:-copy}"
task_repository="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
task_container_id=''

docker_local() {
  env -u DOCKER_HOST -u DOCKER_CONTEXT -u DOCKER_TLS -u DOCKER_TLS_VERIFY -u DOCKER_CERT_PATH \
    docker --host=unix:///var/run/docker.sock "$@"
}
cleanup() {
  if [[ -n "$task_container_id" ]]; then
    docker_local rm --force --volumes "$task_container_id" >/dev/null
  fi
}
trap cleanup EXIT

task_container_id="$(docker_local run --detach \
  --label 3dps.task=m02-disposable-tests \
  --publish 127.0.0.1::5432 \
  --env POSTGRES_USER=3dps_test \
  --env POSTGRES_PASSWORD=m02-disposable-test-only \
  --env POSTGRES_DB=3dps_test_auth \
  postgres:16-bookworm@sha256:5264710be20f409750ac6dc4e5706dcef929c87e241605463f0f9aefa932a8d9)"

task_ready=false
for task_attempt in {1..30}; do
  if docker_local exec "$task_container_id" pg_isready -U 3dps_test -d 3dps_test_auth >/dev/null; then
    task_ready=true
    break
  fi
  sleep 1
done
if [[ "$task_ready" != true ]]; then
  echo 'Disposable PostgreSQL did not become ready.' >&2
  exit 1
fi
task_bind="$(docker_local port "$task_container_id" 5432/tcp)"
task_port="${task_bind##*:}"
export TEST_DATABASE_URL="postgresql+asyncpg://3dps_test:m02-disposable-test-only@127.0.0.1:${task_port}/3dps_test_auth"
cd "$task_repository/backend"
uv sync --frozen
.venv/bin/pytest -q
