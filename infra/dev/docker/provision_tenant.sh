#!/usr/bin/env bash
# Helper script to provision a new tenant site inside the platform dev bench (ERP-003)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"

if [ $# -lt 1 ]; then
    echo "Usage: COMPOSE_PROJECT_NAME=<project> $0 <tenant-id> [country: SA|AE|EG|QA] [site-name] [extra flags...]" >&2
    echo "Example: COMPOSE_PROJECT_NAME=platform-local $0 acme-trading SA" >&2
    exit 1
fi

PROJECT_NAME="${COMPOSE_PROJECT_NAME:-}"
if [ -z "${PROJECT_NAME}" ]; then
    echo "Error: COMPOSE_PROJECT_NAME is not set (for example: export COMPOSE_PROJECT_NAME=platform-local)." >&2
    exit 1
fi

TENANT_ID="$1"
COUNTRY="${2:-SA}"

echo "=== Provisioning tenant '${TENANT_ID}' (${COUNTRY}) on Compose project '${PROJECT_NAME}' ===" >&2

CMD=(
    python3 "${REPO_ROOT}/scripts/provision_tenant_site.py"
    --tenant-id "${TENANT_ID}"
    --country "${COUNTRY}"
    --compose-project "${PROJECT_NAME}"
    --compose-file "${SCRIPT_DIR}/docker-compose.dev.yml"
    --service engine
)

if [ $# -ge 3 ] && [ -n "${3}" ]; then
    CMD+=(--site-name "$3")
fi

if [ $# -ge 4 ]; then
    CMD+=("${@:4}")
fi

exec "${CMD[@]}"
