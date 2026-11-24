"""Build and verify staging release manifests for production promotion.

Manifest schema credit-scoring.staging-release.v1 proves images were published
and (for deploy mode) smoke-tested by a successful staging orchestrator run.
Production must consume digests from a verified manifest — not free-form inputs.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any

SCHEMA = "credit-scoring.staging-release.v1"
MANIFEST_NAME = "staging-release.json"
STAGING_WORKFLOW_NAME = "CI/CD Orchestrator"


def _require_digest_ref(ref: str, label: str) -> str:
    text = (ref or "").strip()
    if not text or "@sha256:" not in text:
        raise ValueError(f"{label} must be image@sha256:digest, got {ref!r}")
    if ":latest" in text.lower().split("@", 1)[0]:
        raise ValueError(f"{label} must not use :latest")
    digest = text.split("@", 1)[1]
    if not digest.startswith("sha256:") or len(digest) < len("sha256:") + 64:
        raise ValueError(f"{label} has invalid digest: {digest}")
    return text


def build_manifest(
    *,
    git_sha: str,
    api_ref: str,
    models_ref: str,
    frontend_ref: str,
    staging_workflow_run_id: str | int,
    mode: str,
    smoke: dict[str, Any] | None = None,
    registry: str = "ghcr.io",
) -> dict[str, Any]:
    mode_norm = mode.strip().lower()
    if mode_norm not in {"publish", "deploy"}:
        raise ValueError("mode must be publish or deploy")

    smoke = smoke or {}
    smoke_ok = bool(smoke.get("ok"))
    if mode_norm == "deploy" and not smoke_ok:
        raise ValueError("deploy mode requires smoke.ok == true")

    status = (
        "staging_verified"
        if mode_norm == "deploy" and smoke_ok
        else "published_not_deployed"
    )

    return {
        "schema": SCHEMA,
        "git_sha": git_sha.strip().lower(),
        "registry": registry,
        "images": {
            "api": _require_digest_ref(api_ref, "api"),
            "models": _require_digest_ref(models_ref, "models"),
            "frontend": _require_digest_ref(frontend_ref, "frontend"),
        },
        "staging_workflow_name": STAGING_WORKFLOW_NAME,
        "staging_workflow_run_id": str(staging_workflow_run_id),
        "mode": mode_norm,
        "smoke": {
            "ok": smoke_ok,
            "failed": smoke.get("failed"),
            "base_url": smoke.get("base_url"),
            "host": smoke.get("host"),
        },
        "status": status,
    }


def verify_manifest_for_production(
    manifest: dict[str, Any],
    *,
    expect_git_sha: str,
    expect_run_id: str | None = None,
    allow_api_ref: str | None = None,
    allow_models_ref: str | None = None,
    allow_frontend_ref: str | None = None,
) -> dict[str, Any]:
    """Validate manifest; optionally ensure claimed digests match (no substitution)."""
    errors: list[str] = []

    if manifest.get("schema") != SCHEMA:
        errors.append(f"schema mismatch: {manifest.get('schema')}")
    if str(manifest.get("status")) != "staging_verified":
        errors.append(f"status must be staging_verified, got {manifest.get('status')}")
    if str(manifest.get("mode")) != "deploy":
        errors.append(f"mode must be deploy, got {manifest.get('mode')}")
    if str(manifest.get("staging_workflow_name")) != STAGING_WORKFLOW_NAME:
        errors.append("staging_workflow_name mismatch")

    git_sha = str(manifest.get("git_sha") or "").lower()
    if not git_sha or git_sha != expect_git_sha.strip().lower():
        errors.append(f"git_sha mismatch: manifest={git_sha} expected={expect_git_sha}")

    if expect_run_id is not None:
        if str(manifest.get("staging_workflow_run_id")) != str(expect_run_id):
            errors.append("staging_workflow_run_id mismatch")

    smoke = manifest.get("smoke") or {}
    if not smoke.get("ok"):
        errors.append("staging smoke not ok")

    images = manifest.get("images") or {}
    for key in ("api", "models", "frontend"):
        try:
            _require_digest_ref(str(images.get(key) or ""), key)
        except ValueError as exc:
            errors.append(str(exc))

    claimed = {
        "api": allow_api_ref,
        "models": allow_models_ref,
        "frontend": allow_frontend_ref,
    }
    for key, claimed_ref in claimed.items():
        if claimed_ref is None or claimed_ref == "":
            continue
        actual = str(images.get(key) or "")
        if actual != claimed_ref.strip():
            errors.append(
                f"digest substitution rejected for {key}: "
                f"claimed={claimed_ref!r} manifest={actual!r}"
            )

    return {
        "ok": not errors,
        "errors": errors,
        "git_sha": git_sha,
        "images": images,
        "staging_workflow_run_id": manifest.get("staging_workflow_run_id"),
        "status": manifest.get("status"),
    }


def _api_get(url: str, token: str) -> Any:
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "credit-scoring-staging-release",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _api_get_bytes(url: str, token: str) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "credit-scoring-staging-release",
        },
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.read()


def fetch_workflow_run(
    *, owner: str, repo: str, run_id: str, token: str
) -> dict[str, Any]:
    url = f"https://api.github.com/repos/{owner}/{repo}/actions/runs/{run_id}"
    return _api_get(url, token)


def download_manifest_from_run(
    *,
    owner: str,
    repo: str,
    run_id: str,
    token: str,
    artifact_name_prefix: str = "staging-release-",
) -> dict[str, Any]:
    """Download staging-release.json from a successful orchestrator run artifact."""
    run = fetch_workflow_run(owner=owner, repo=repo, run_id=run_id, token=token)
    if str(run.get("name")) != STAGING_WORKFLOW_NAME:
        raise ValueError(
            f"run {run_id} workflow is {run.get('name')!r}, "
            f"expected {STAGING_WORKFLOW_NAME!r}"
        )
    if str(run.get("status")) != "completed" or str(run.get("conclusion")) != "success":
        raise ValueError(
            f"staging run {run_id} not successful "
            f"(status={run.get('status')} conclusion={run.get('conclusion')})"
        )

    arts_url = (
        f"https://api.github.com/repos/{owner}/{repo}/actions/runs/{run_id}/artifacts"
    )
    payload = _api_get(arts_url, token)
    artifacts = list(payload.get("artifacts") or [])
    chosen = None
    for art in artifacts:
        name = str(art.get("name") or "")
        if name.startswith(artifact_name_prefix) or name == "staging-release":
            chosen = art
            break
    if chosen is None:
        raise FileNotFoundError(
            f"no staging-release artifact on run {run_id}; "
            f"found={[a.get('name') for a in artifacts]}"
        )

    zip_bytes = _api_get_bytes(str(chosen["archive_download_url"]), token)
    with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
        names = zf.namelist()
        target = None
        for n in names:
            if n.endswith(MANIFEST_NAME) or n == MANIFEST_NAME:
                target = n
                break
        if target is None:
            raise FileNotFoundError(f"{MANIFEST_NAME} missing in artifact: {names}")
        raw = zf.read(target).decode("utf-8")
    manifest = json.loads(raw)

    # Bind run identity into verification context.
    if str(manifest.get("staging_workflow_run_id")) not in {"", str(run_id)}:
        # Prefer explicit match; if empty, fill from run.
        pass
    if not manifest.get("staging_workflow_run_id"):
        manifest["staging_workflow_run_id"] = str(run_id)

    head_sha = str(run.get("head_sha") or "").lower()
    if head_sha and head_sha != str(manifest.get("git_sha") or "").lower():
        raise ValueError(
            f"run head_sha {head_sha} != manifest git_sha {manifest.get('git_sha')}"
        )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    build = sub.add_parser("build", help="Write a staging release manifest")
    build.add_argument("--git-sha", required=True)
    build.add_argument("--api-ref", required=True)
    build.add_argument("--models-ref", required=True)
    build.add_argument("--frontend-ref", required=True)
    build.add_argument("--run-id", required=True)
    build.add_argument("--mode", required=True, choices=["publish", "deploy"])
    build.add_argument("--smoke-json", default="")
    build.add_argument("--output", required=True)

    verify = sub.add_parser("verify", help="Verify manifest for production")
    verify.add_argument("--manifest", required=True)
    verify.add_argument("--expect-git-sha", required=True)
    verify.add_argument("--expect-run-id", default="")
    verify.add_argument("--claim-api-ref", default="")
    verify.add_argument("--claim-models-ref", default="")
    verify.add_argument("--claim-frontend-ref", default="")
    verify.add_argument("--output", default="")

    fetch = sub.add_parser("fetch", help="Fetch manifest from a staging Actions run")
    fetch.add_argument("--run-id", required=True)
    fetch.add_argument("--expect-git-sha", required=True)
    fetch.add_argument("--owner", default=os.environ.get("GITHUB_REPOSITORY_OWNER", ""))
    fetch.add_argument(
        "--repo",
        default=(os.environ.get("GITHUB_REPOSITORY", "").split("/")[-1] or ""),
    )
    fetch.add_argument("--claim-api-ref", default="")
    fetch.add_argument("--claim-models-ref", default="")
    fetch.add_argument("--claim-frontend-ref", default="")
    fetch.add_argument("--output", required=True)

    args = parser.parse_args()

    try:
        if args.cmd == "build":
            smoke = {}
            if args.smoke_json:
                smoke = json.loads(Path(args.smoke_json).read_text(encoding="utf-8"))
            manifest = build_manifest(
                git_sha=args.git_sha,
                api_ref=args.api_ref,
                models_ref=args.models_ref,
                frontend_ref=args.frontend_ref,
                staging_workflow_run_id=args.run_id,
                mode=args.mode,
                smoke=smoke,
            )
            out = Path(args.output)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            print(json.dumps(manifest, indent=2))
            return 0

        if args.cmd == "verify":
            manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
            result = verify_manifest_for_production(
                manifest,
                expect_git_sha=args.expect_git_sha,
                expect_run_id=args.expect_run_id or None,
                allow_api_ref=args.claim_api_ref or None,
                allow_models_ref=args.claim_models_ref or None,
                allow_frontend_ref=args.claim_frontend_ref or None,
            )
            if args.output:
                Path(args.output).write_text(
                    json.dumps(result, indent=2), encoding="utf-8"
                )
            print(json.dumps(result, indent=2))
            return 0 if result["ok"] else 2

        if args.cmd == "fetch":
            token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
            if not token or not args.owner or not args.repo:
                print("GITHUB_TOKEN/owner/repo required for fetch", file=sys.stderr)
                return 2
            manifest = download_manifest_from_run(
                owner=args.owner,
                repo=args.repo,
                run_id=str(args.run_id),
                token=token,
            )
            result = verify_manifest_for_production(
                manifest,
                expect_git_sha=args.expect_git_sha,
                expect_run_id=str(args.run_id),
                allow_api_ref=args.claim_api_ref or None,
                allow_models_ref=args.claim_models_ref or None,
                allow_frontend_ref=args.claim_frontend_ref or None,
            )
            out = Path(args.output)
            out.parent.mkdir(parents=True, exist_ok=True)
            if not result["ok"]:
                out.write_text(json.dumps(result, indent=2), encoding="utf-8")
                print(json.dumps(result, indent=2))
                return 2
            out.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            # Also write images.env-style lines for the workflow
            images = manifest["images"]
            print(f"api_ref={images['api']}")
            print(f"models_ref={images['models']}")
            print(f"frontend_ref={images['frontend']}")
            print(json.dumps(result, indent=2))
            return 0
    except (ValueError, FileNotFoundError, json.JSONDecodeError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except urllib.error.HTTPError as exc:
        print(f"GitHub API error: {exc}", file=sys.stderr)
        return 2

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
