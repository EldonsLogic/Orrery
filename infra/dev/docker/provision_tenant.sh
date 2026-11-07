#!/usr/bin/env bash
# Helper script to provision a new tenant site inside the Orrery dev bench (ERP-003)
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"

CONTAINER="${CONTAINER_NAME:-ce-engine-dev}"

if [ $# -lt 1 ]; then
    echo "Usage: $0 <tenant-id> [country: SA|AE|EG|QA] [site-name]"
    echo "Example: $0 acme-trading SA"
    exit 1
fi

TENANT_ID="$1"
COUNTRY="${2:-SA}"
SITE_NAME="${3:-${TENANT_ID}.localhost}"

echo "=== Provisioning tenant '${TENANT_ID}' (${COUNTRY}) on container '${CONTAINER}' ==="

python3 "${REPO_ROOT}/scripts/provision_tenant_site.py" \
    --tenant-id "${TENANT_ID}" \
    --country "${COUNTRY}" \
    --site-name "${SITE_NAME}" \
    --container "${CONTAINER}" \
    "${@:4}"
