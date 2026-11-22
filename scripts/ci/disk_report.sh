#!/usr/bin/env bash
# Disk / Docker / kind diagnostics for GitHub-hosted runners (and local Linux).
set -euo pipefail

LABEL="${1:-disk-report}"
echo "===== DISK REPORT: ${LABEL} ====="
echo "--- df -h ---"
df -h || true
echo "--- df -i ---"
df -i || true
echo "--- docker system df ---"
docker system df || true
echo "--- docker image ls ---"
docker image ls --digests || true

for img in credit-scoring-api:stage3a credit-scoring-models:stage3a; do
  if docker image inspect "${img}" >/dev/null 2>&1; then
    bytes="$(docker image inspect -f '{{.Size}}' "${img}")"
    echo "image ${img} size_bytes=${bytes} size_mb=$((bytes / 1024 / 1024))"
  else
    echo "image ${img}: not present"
  fi
done

if command -v kind >/dev/null 2>&1; then
  if kind get clusters 2>/dev/null | grep -qx 'credit-scoring'; then
    echo "--- kind node df (credit-scoring-control-plane) ---"
    docker exec credit-scoring-control-plane df -h || true
    docker exec credit-scoring-control-plane df -i || true
  else
    echo "kind cluster 'credit-scoring': not present"
  fi
fi
echo "===== END DISK REPORT: ${LABEL} ====="
