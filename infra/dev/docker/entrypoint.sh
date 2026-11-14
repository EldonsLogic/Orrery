#!/usr/bin/env bash
set -e

BENCH_DIR="${HOME}/frappe-bench"
export PATH="${BENCH_DIR}/env/bin:${PATH}"

SITES_DIR="${BENCH_DIR}/sites"
APPS_TXT="${SITES_DIR}/apps.txt"
CONFIG_FILE="${SITES_DIR}/common_site_config.json"

DB_HOST="${DB_HOST:-mariadb}"
DB_PORT="${DB_PORT:-3306}"
REDIS_CACHE_HOST="${REDIS_CACHE_HOST:-redis-cache}"
REDIS_QUEUE_HOST="${REDIS_QUEUE_HOST:-redis-queue}"

echo "=== Initializing Orrery Engine Dev Environment (Frappe/ERPNext/HRMS v15) ==="

# 1. Generate common_site_config.json if not present or needs update
mkdir -p "${SITES_DIR}"

# Link the image's built assets and compiled translations into sites/, as the
# upstream image entrypoint does; the engine reads them from sites/assets.
rm -rf "${SITES_DIR}/assets"
ln -s "${BENCH_DIR}/assets" "${SITES_DIR}/assets"
cat <<EOF > "${CONFIG_FILE}"
{
  "db_host": "${DB_HOST}",
  "db_port": ${DB_PORT},
  "redis_cache": "redis://${REDIS_CACHE_HOST}:6379",
  "redis_queue": "redis://${REDIS_QUEUE_HOST}:6379",
  "redis_socketio": "redis://${REDIS_QUEUE_HOST}:6379",
  "auto_update": false,
  "developer_mode": 1
}
EOF

# 2. Register mounted change_engine app if available
if [ -d "${BENCH_DIR}/apps/change_engine" ]; then
    echo "Found change_engine app; installing in editable mode..."
    if ! pip install -e "${BENCH_DIR}/apps/change_engine" --no-deps; then
        echo "Cannot install change_engine app" >&2
        exit 1
    fi
fi

# 3. Ensure apps.txt contains the pinned application set
touch "${APPS_TXT}"
# The upstream image may ship apps.txt without a final newline.
if [ -s "${APPS_TXT}" ] && [ "$(tail -c 1 "${APPS_TXT}" | wc -l)" -eq 0 ]; then
    printf '\n' >> "${APPS_TXT}"
fi
for app in frappe erpnext hrms change_engine; do
    if [ -d "${BENCH_DIR}/apps/${app}" ] && ! grep -qx "${app}" "${APPS_TXT}" 2>/dev/null; then
        echo "${app}" >> "${APPS_TXT}"
    fi
done

# 4. Handle subcommands or start headless engine server
if [ "$1" = "start" ]; then
    SITE_NAME="${SITE_NAME:-dev.localhost}"
    echo "Starting engine runtime on 0.0.0.0:8000 for default site ${SITE_NAME}..."
    exec gunicorn \
        --chdir="${BENCH_DIR}/sites" \
        --bind=0.0.0.0:8000 \
        --threads=4 \
        --workers=2 \
        --worker-class=gthread \
        --worker-tmp-dir=/dev/shm \
        --timeout=120 \
        frappe.app:application
elif [ "$1" = "worker" ]; then
    echo "Starting background queue worker..."
    exec bench worker --queue default,short,long
else
    exec "$@"
fi
