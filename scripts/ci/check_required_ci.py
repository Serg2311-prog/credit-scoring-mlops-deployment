"""Gate CD on successful required CI workflow conclusions for a git SHA.

Uses Actions workflow runs for head_sha (preferred) so job display names do not
matter. Required workflows must all conclude success for the same commit.

Exit codes:
  0 — all required workflows succeeded
  2 — hard failure (failed/cancelled/skipped/timed_out/stale tip/API error)
  3 — incomplete (missing or still pending) when --incomplete-as-wait
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_REQUIRED = [
    "CI Python",
    "CI Docker",
    "CI Infrastructure",
    "CI Kubernetes",
    "CI Airflow DAG",
]

HARD_FAIL_CONCLUSIONS = frozenset(
    {
        "failure",
        "cancelled",
        "canceled",
        "timed_out",
        "action_required",
        "startup_failure",
        "stale",
        "skipped",
        "neutral",
    }
)


def _api_get(url: str, token: str) -> Any:
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "credit-scoring-ci-gate",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _parse_ts(value: str | None) -> datetime:
    if not value:
        return datetime.fromtimestamp(0, tz=timezone.utc)
    text = value.replace("Z", "+00:00")
    return datetime.fromisoformat(text)


def _match_required(required: str, workflow_name: str) -> bool:
    a = required.strip().lower()
    b = workflow_name.strip().lower()
    return a == b or a in b or b in a


def select_latest_runs_by_workflow(
    runs: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Keep the newest run per workflow name (updated_at, then run_attempt)."""
    best: dict[str, dict[str, Any]] = {}
    for run in runs:
        name = str(run.get("name") or "")
        if not name:
            continue
        prev = best.get(name)
        if prev is None:
            best[name] = run
            continue
        cur_key = (_parse_ts(run.get("updated_at")), int(run.get("run_attempt") or 1))
        prev_key = (
            _parse_ts(prev.get("updated_at")),
            int(prev.get("run_attempt") or 1),
        )
        if cur_key >= prev_key:
            best[name] = run
    return best


def evaluate_required_runs(
    *,
    sha: str,
    required: list[str],
    latest_by_name: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Classify required workflows against the latest run per workflow name."""
    missing: list[str] = []
    pending: list[str] = []
    failed: list[str] = []
    skipped: list[str] = []
    ok: list[str] = []
    matched: dict[str, Any] = {}

    for req in required:
        match_name = None
        match_run = None
        for name, run in latest_by_name.items():
            if _match_required(req, name):
                match_name = name
                match_run = run
                break
        if match_run is None:
            missing.append(req)
            continue

        status = str(match_run.get("status") or "")
        conclusion = str(match_run.get("conclusion") or "")
        info = {
            "required": req,
            "workflow_name": match_name,
            "status": status,
            "conclusion": conclusion,
            "id": match_run.get("id"),
            "html_url": match_run.get("html_url"),
            "run_attempt": match_run.get("run_attempt"),
            "head_sha": match_run.get("head_sha"),
        }
        matched[req] = info

        if status != "completed":
            pending.append(f"{req}: status={status}")
            continue
        if conclusion == "success":
            ok.append(req)
            continue
        if conclusion == "skipped":
            skipped.append(f"{req}: conclusion=skipped")
            failed.append(f"{req}: conclusion=skipped")
            continue
        if conclusion in HARD_FAIL_CONCLUSIONS or not conclusion:
            failed.append(f"{req}: conclusion={conclusion or 'null'}")
            continue
        failed.append(f"{req}: conclusion={conclusion}")

    return {
        "sha": sha,
        "required": required,
        "ok": ok,
        "missing": missing,
        "pending": pending,
        "failed": failed,
        "skipped": skipped,
        "matched": matched,
        "passed": not missing and not pending and not failed,
        "incomplete": bool(missing or pending) and not failed,
    }


def fetch_workflow_runs_for_sha(
    *, owner: str, repo: str, sha: str, token: str
) -> list[dict[str, Any]]:
    q = urllib.parse.urlencode({"head_sha": sha, "per_page": "100"})
    url = f"https://api.github.com/repos/{owner}/{repo}/actions/runs?{q}"
    payload = _api_get(url, token)
    return list(payload.get("workflow_runs") or [])


def fetch_branch_tip(*, owner: str, repo: str, branch: str, token: str) -> str:
    quoted = urllib.parse.quote(branch)
    url = f"https://api.github.com/repos/{owner}/{repo}/commits/{quoted}"
    payload = _api_get(url, token)
    return str(payload.get("sha") or "")


def check_commit_statuses(
    *,
    owner: str,
    repo: str,
    sha: str,
    token: str,
    required: list[str],
    expect_branch_tip: str = "",
) -> dict[str, Any]:
    runs = fetch_workflow_runs_for_sha(owner=owner, repo=repo, sha=sha, token=token)
    latest = select_latest_runs_by_workflow(runs)
    report = evaluate_required_runs(sha=sha, required=required, latest_by_name=latest)
    report["observed_workflows"] = [
        {
            "name": name,
            "status": run.get("status"),
            "conclusion": run.get("conclusion"),
            "id": run.get("id"),
            "run_attempt": run.get("run_attempt"),
            "updated_at": run.get("updated_at"),
        }
        for name, run in sorted(latest.items())
    ]

    if expect_branch_tip:
        tip = fetch_branch_tip(
            owner=owner, repo=repo, branch=expect_branch_tip, token=token
        )
        report["branch_tip"] = {"branch": expect_branch_tip, "sha": tip}
        if tip and tip.lower() != sha.lower():
            report["passed"] = False
            report["incomplete"] = False
            report["failed"] = list(report.get("failed") or []) + [
                f"stale SHA: deploy {sha} but {expect_branch_tip} tip is {tip}"
            ]
            report["stale"] = True
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sha", required=True)
    parser.add_argument(
        "--owner", default=os.environ.get("GITHUB_REPOSITORY_OWNER", "")
    )
    parser.add_argument(
        "--repo",
        default=(os.environ.get("GITHUB_REPOSITORY", "").split("/")[-1] or ""),
    )
    parser.add_argument(
        "--required",
        nargs="*",
        default=DEFAULT_REQUIRED,
        help="Required workflow name substrings",
    )
    parser.add_argument(
        "--allow-local-skip",
        action="store_true",
        help="Exit 0 when GITHUB_TOKEN is absent (local kind CD only)",
    )
    parser.add_argument(
        "--incomplete-as-wait",
        action="store_true",
        help="Exit 3 when checks are missing/pending (auto staging wait)",
    )
    parser.add_argument(
        "--expect-branch-tip",
        default="",
        help="Fail if SHA is not the tip of this branch (stale protection)",
    )
    parser.add_argument("--output", default="", help="Optional JSON report path")
    args = parser.parse_args()

    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
    report: dict[str, Any]
    if not token or not args.owner or not args.repo:
        report = {
            "sha": args.sha,
            "passed": bool(args.allow_local_skip),
            "mode": "local_skip" if args.allow_local_skip else "unavailable",
            "message": (
                "GITHUB_TOKEN/owner/repo unavailable; "
                + (
                    "allowed for local CD verification"
                    if args.allow_local_skip
                    else "refusing CD gate"
                )
            ),
        }
        if args.output:
            path = Path(args.output)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
        return 0 if args.allow_local_skip else 2

    try:
        report = check_commit_statuses(
            owner=args.owner,
            repo=args.repo,
            sha=args.sha,
            token=token,
            required=list(args.required),
            expect_branch_tip=args.expect_branch_tip,
        )
    except urllib.error.HTTPError as exc:
        print(f"GitHub API error: {exc}", file=sys.stderr)
        return 2

    if args.output:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))

    if report.get("passed"):
        return 0
    if (
        args.incomplete_as_wait
        and report.get("incomplete")
        and not report.get("failed")
    ):
        return 3
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
