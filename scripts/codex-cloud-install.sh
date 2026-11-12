#!/usr/bin/env bash
set -euo pipefail

task_repository="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$task_repository"
test -f AGENTS.md
test -f backend/uv.lock
test -f miniapp/package-lock.json
test -f tools/api-types/package-lock.json

task_status_before="$(git status --porcelain)"
command -v uv >/dev/null
command -v node >/dev/null
command -v npm >/dev/null

task_node_version="$(tr -d '[:space:]' < miniapp/.node-version)"
if [[ "$(node --version)" != "v${task_node_version}" ]]; then
  echo "Required Node version: ${task_node_version}" >&2
  exit 1
fi

export UV_CACHE_DIR=/tmp/3dps-uv-cache
export UV_LINK_MODE=copy
export UV_PYTHON_INSTALL_DIR="$task_repository/.local/python"
export npm_config_cache=/tmp/3dps-npm-cache
export PLAYWRIGHT_BROWSERS_PATH="$task_repository/.local/playwright-browsers"

(cd backend && uv sync --frozen)
(cd miniapp && npm ci)
(cd tools/api-types && npm ci)

if [[ ! -x /usr/bin/chromium ]]; then
  (cd miniapp && npx --no-install playwright install chromium)
fi

backend/.venv/bin/python -c 'import fastapi, sqlalchemy, asyncpg, alembic, PIL'
miniapp/node_modules/.bin/tsc --version

if [[ "$(git status --porcelain)" != "$task_status_before" ]]; then
  echo 'Repository changes differ from the pre-install state; inspect git status.' >&2
  exit 1
fi

echo 'Dependencies installed; existing repository changes preserved.'
