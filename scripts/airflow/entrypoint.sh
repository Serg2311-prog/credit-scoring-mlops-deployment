#!/usr/bin/env bash
# Local Stage 7 Airflow entrypoint (NOT production).
# Ordered init: migrate DB → ensure admin user → start webserver → wait health → scheduler.
set -euo pipefail

echo "[airflow-entrypoint] starting Stage 7 local demo init"
echo "[airflow-entrypoint] AIRFLOW_HOME=${AIRFLOW_HOME:-/opt/airflow}"
echo "[airflow-entrypoint] CREDIT_SCORING_ROOT=${CREDIT_SCORING_ROOT:-/opt/credit-scoring}"

AIRFLOW_HOME="${AIRFLOW_HOME:-/opt/airflow}"
mkdir -p "${AIRFLOW_HOME}/logs" "${AIRFLOW_HOME}/dags"

echo "[airflow-entrypoint] 1/4 airflow db migrate"
airflow db migrate

USERNAME="${_AIRFLOW_WWW_USER_USERNAME:-admin}"
PASSWORD="${_AIRFLOW_WWW_USER_PASSWORD:-admin}"

echo "[airflow-entrypoint] 2/4 ensure web user '${USERNAME}'"
if airflow users list 2>/dev/null | grep -qE "(^|\\s)${USERNAME}(\\s|$)"; then
  echo "[airflow-entrypoint] user already exists"
else
  airflow users create \
    --username "${USERNAME}" \
    --password "${PASSWORD}" \
    --firstname Admin \
    --lastname Local \
    --role Admin \
    --email admin@example.com
fi

echo "[airflow-entrypoint] 3/4 start webserver on :8080"
airflow webserver --port 8080 &
WEB_PID=$!

echo "[airflow-entrypoint] waiting for webserver health (pid=${WEB_PID})"
READY=0
for i in $(seq 1 60); do
  if curl -sf "http://127.0.0.1:8080/health" >/dev/null 2>&1; then
    echo "[airflow-entrypoint] webserver healthy after ${i}s"
    READY=1
    break
  fi
  if ! kill -0 "${WEB_PID}" 2>/dev/null; then
    echo "[airflow-entrypoint] ERROR: webserver process exited early" >&2
    wait "${WEB_PID}" || true
    exit 1
  fi
  sleep 1
done

if [[ "${READY}" -ne 1 ]]; then
  echo "[airflow-entrypoint] ERROR: webserver health check timed out" >&2
  kill "${WEB_PID}" 2>/dev/null || true
  exit 1
fi

cleanup() {
  echo "[airflow-entrypoint] shutting down webserver pid=${WEB_PID}"
  kill "${WEB_PID}" 2>/dev/null || true
  wait "${WEB_PID}" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "[airflow-entrypoint] 4/4 start scheduler (foreground)"
exec airflow scheduler
