"""Unit tests for required CI gate (5 workflows, conclusions, stale tip)."""

from __future__ import annotations

from scripts.ci.check_required_ci import (
    DEFAULT_REQUIRED,
    evaluate_required_runs,
    select_latest_runs_by_workflow,
)


def test_default_required_includes_airflow():
    assert "CI Airflow DAG" in DEFAULT_REQUIRED
    assert len(DEFAULT_REQUIRED) == 5


def _run(
    name: str,
    status: str,
    conclusion: str | None,
    attempt: int = 1,
    ts: str = "2026-01-01T00:00:00Z",
):
    return {
        "name": name,
        "status": status,
        "conclusion": conclusion,
        "run_attempt": attempt,
        "updated_at": ts,
        "id": attempt,
        "html_url": f"https://example/{name}",
        "head_sha": "abc",
    }


def test_all_success_passes():
    latest = {n: _run(n, "completed", "success") for n in DEFAULT_REQUIRED}
    report = evaluate_required_runs(
        sha="abc", required=list(DEFAULT_REQUIRED), latest_by_name=latest
    )
    assert report["passed"] is True
    assert report["missing"] == []
    assert report["pending"] == []
    assert report["failed"] == []


def test_missing_workflow():
    latest = {
        n: _run(n, "completed", "success")
        for n in DEFAULT_REQUIRED
        if n != "CI Airflow DAG"
    }
    report = evaluate_required_runs(
        sha="abc", required=list(DEFAULT_REQUIRED), latest_by_name=latest
    )
    assert report["passed"] is False
    assert "CI Airflow DAG" in report["missing"]
    assert report["incomplete"] is True


def test_pending_in_progress():
    latest = {n: _run(n, "completed", "success") for n in DEFAULT_REQUIRED}
    latest["CI Python"] = _run("CI Python", "in_progress", None)
    report = evaluate_required_runs(
        sha="abc", required=list(DEFAULT_REQUIRED), latest_by_name=latest
    )
    assert report["passed"] is False
    assert report["pending"]
    assert report["incomplete"] is True


def test_failed_cancelled_skipped():
    for conclusion in ("failure", "cancelled", "skipped", "timed_out"):
        latest = {n: _run(n, "completed", "success") for n in DEFAULT_REQUIRED}
        latest["CI Docker"] = _run("CI Docker", "completed", conclusion)
        report = evaluate_required_runs(
            sha="abc", required=list(DEFAULT_REQUIRED), latest_by_name=latest
        )
        assert report["passed"] is False, conclusion
        assert report["failed"], conclusion
        assert report["incomplete"] is False, conclusion


def test_rerun_prefers_latest_attempt():
    runs = [
        _run("CI Python", "completed", "failure", attempt=1, ts="2026-01-01T00:00:00Z"),
        _run("CI Python", "completed", "success", attempt=2, ts="2026-01-01T01:00:00Z"),
        _run("CI Docker", "completed", "success"),
        _run("CI Infrastructure", "completed", "success"),
        _run("CI Kubernetes", "completed", "success"),
        _run("CI Airflow DAG", "completed", "success"),
    ]
    latest = select_latest_runs_by_workflow(runs)
    assert latest["CI Python"]["conclusion"] == "success"
    assert latest["CI Python"]["run_attempt"] == 2
    report = evaluate_required_runs(
        sha="abc", required=list(DEFAULT_REQUIRED), latest_by_name=latest
    )
    assert report["passed"] is True


def test_stale_marker_via_failed_list_shape():
    # Stale tip is applied in check_commit_statuses; evaluate itself has no tip.
    # Ensure failed+cancelled path does not look like incomplete wait.
    latest = {n: _run(n, "completed", "success") for n in DEFAULT_REQUIRED}
    latest["CI Kubernetes"] = _run("CI Kubernetes", "completed", "cancelled")
    report = evaluate_required_runs(
        sha="abc", required=list(DEFAULT_REQUIRED), latest_by_name=latest
    )
    assert report["incomplete"] is False
    assert any("cancelled" in x for x in report["failed"])
