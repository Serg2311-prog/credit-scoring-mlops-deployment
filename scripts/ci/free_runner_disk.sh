#!/usr/bin/env bash
# Reclaim disk on GitHub-hosted Ubuntu runners only.
# Safe: does not remove Docker/containerd engines, Python, or apt base libs.
# Skips cleanup on non-hosted / local machines.
set -euo pipefail

if [[ "${GITHUB_ACTIONS:-}" != "true" ]]; then
  echo "free_runner_disk: skip (not GitHub Actions)"
  exit 0
fi

# actions/runner sets RUNNER_ENVIRONMENT=github-hosted on hosted VMs.
if [[ "${RUNNER_ENVIRONMENT:-}" != "github-hosted" && -z "${RUNNER_TOOL_CACHE:-}" ]]; then
  echo "free_runner_disk: skip (does not look like a hosted runner)"
  exit 0
fi

echo "free_runner_disk: reclaiming preinstalled toolchains on hosted runner"
df -h / || true

# Large unused SDKs / toolchains (~20–40 GB combined on ubuntu-latest).
sudo rm -rf \
  /usr/share/dotnet \
  /usr/local/lib/android \
  /opt/ghc \
  /usr/local/share/boost \
  /usr/local/graalvm \
  /usr/local/.ghcup \
  /usr/share/swift \
  /opt/hostedtoolcache/CodeQL \
  /usr/local/share/powershell \
  /usr/share/az_* \
  /opt/az \
  /usr/lib/jvm \
  /opt/microsoft \
  2>/dev/null || true

sudo apt-get clean >/dev/null 2>&1 || true

# Drop unused pre-pulled images/build cache from the runner image (not our builds yet).
docker system prune -af --volumes >/dev/null 2>&1 || true

# Prefer the larger /mnt volume for temp tarballs used by kind load.
if [[ -d /mnt ]]; then
  sudo mkdir -p /mnt/tmp
  sudo chmod 1777 /mnt/tmp
  # Export for subsequent steps in this job via GITHUB_ENV when available.
  if [[ -n "${GITHUB_ENV:-}" ]]; then
    echo "TMPDIR=/mnt/tmp" >> "${GITHUB_ENV}"
    echo "TMP=/mnt/tmp" >> "${GITHUB_ENV}"
    echo "TEMP=/mnt/tmp" >> "${GITHUB_ENV}"
  fi
  export TMPDIR=/mnt/tmp
fi

echo "free_runner_disk: done"
df -h / /mnt 2>/dev/null || df -h /
