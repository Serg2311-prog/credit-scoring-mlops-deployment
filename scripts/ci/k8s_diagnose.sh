#!/usr/bin/env bash
# Collect kind/kubectl diagnostics even when rollout/smoke fails.
# Writes text files under artifacts/ci/k8s-diagnose/ (created by caller).
set -uo pipefail

OUT_DIR="${1:-artifacts/ci/k8s-diagnose}"
NS="${2:-credit-scoring}"
mkdir -p "${OUT_DIR}"

note() { echo "[k8s-diagnose] $*"; }

run_capture() {
  local name="$1"
  shift
  note "running: $*"
  # Keep going even if kubectl fails (cluster partially up / already torn).
  if "$@" >"${OUT_DIR}/${name}.txt" 2>&1; then
    note "ok: ${name}"
  else
    echo "COMMAND_FAILED exit=$?" >>"${OUT_DIR}/${name}.txt"
    note "failed: ${name} (captured)"
  fi
}

note "namespace=${NS} out=${OUT_DIR}"
run_capture 00-get-ns kubectl get ns "${NS}" -o wide
run_capture 01-get-all kubectl -n "${NS}" get all,cm,secret,pvc -o wide
run_capture 02-get-pods kubectl -n "${NS}" get pods -o wide
run_capture 03-describe-deploy kubectl -n "${NS}" describe deployment credit-scoring-api
run_capture 04-describe-pods kubectl -n "${NS}" describe pods -l app.kubernetes.io/name=credit-scoring-api
run_capture 05-events kubectl -n "${NS}" get events --sort-by=.lastTimestamp
run_capture 06-get-pvc kubectl -n "${NS}" get pvc -o wide
run_capture 07-cm kubectl -n "${NS}" get configmap credit-scoring-api-config -o yaml
run_capture 08-deploy-yaml kubectl -n "${NS}" get deployment credit-scoring-api -o yaml

# Per-pod logs (api + init).
mapfile -t PODS < <(kubectl -n "${NS}" get pods -l app.kubernetes.io/name=credit-scoring-api -o jsonpath='{.items[*].metadata.name}' 2>/dev/null || true)
if [[ ${#PODS[@]} -eq 0 || -z "${PODS[0]:-}" ]]; then
  note "no pods found for log capture"
  echo "no pods" >"${OUT_DIR}/09-pods-list.txt"
else
  printf '%s\n' "${PODS[@]}" >"${OUT_DIR}/09-pods-list.txt"
  idx=0
  for pod in "${PODS[@]}"; do
    run_capture "10-logs-api-${idx}-${pod}" kubectl -n "${NS}" logs "${pod}" -c api --all-containers=false --tail=500
    run_capture "11-logs-init-${idx}-${pod}" kubectl -n "${NS}" logs "${pod}" -c copy-models --tail=200
    run_capture "12-logs-previous-api-${idx}-${pod}" kubectl -n "${NS}" logs "${pod}" -c api --previous --tail=200
    idx=$((idx + 1))
  done
fi

# metrics-server is optional on kind
run_capture 13-top-pods kubectl -n "${NS}" top pods
run_capture 14-top-nodes kubectl top nodes

# Image / dim hints from node (best-effort).
run_capture 15-images-on-node docker exec credit-scoring-control-plane crictl images
run_capture 16-node-df docker exec credit-scoring-control-plane df -h

note "done"
ls -la "${OUT_DIR}" || true
