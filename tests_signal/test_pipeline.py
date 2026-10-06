import fcntl
import json
import shutil
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import duckdb
import pytest

from signal_demo import pipeline
from signal_demo.detection import build_review_queue, fit_reference, monitor
from signal_demo.quality import inspect
from signal_demo.warehouse import build


def test_duckdb_recomputes_expectations_and_baseline_rates(panel, tmp_path):
    c, rows = panel
    quality = inspect(rows, c)
    reference = fit_reference(rows, quality, c)
    scored = monitor(quality, reference, c)
    path = tmp_path / "signal.duckdb"
    qa = build(path, rows, quality, reference, scored, build_review_queue(scored))
    assert (
        qa["status"] == "PASS"
        and len(qa["checks"]) == 26
        and not any(qa["checks"].values())
    )
    with duckdb.connect(str(path), read_only=True) as con:
        assert con.execute(
            "SELECT MIN(expected_count),MAX(expected_count) FROM mart.signal_expectation"
        ).fetchone() == (16.0, 16.0)
        assert (
            con.execute("SELECT COUNT(*) FROM mart.signal_coverage").fetchone()[0] == 46
        )


@pytest.mark.parametrize("corruption", ["residual", "missing_score", "missing_bucket"])
def test_duckdb_detects_changed_or_missing_python_scores(panel, tmp_path, corruption):
    c, rows = panel
    quality = inspect(rows, c)
    reference = fit_reference(rows, quality, c)
    scored = monitor(quality, reference, c)
    if corruption == "residual":
        scored[0]["standardized_residual"] = 9
    elif corruption == "missing_score":
        scored[0]["standardized_residual"] = None
    else:
        scored.pop(0)
    with pytest.raises(ValueError, match="warehouse QA"):
        build(tmp_path / "corrupted.duckdb", rows, quality, reference, scored, [])


@pytest.fixture(scope="module")
def completed(tmp_path_factory):
    path = tmp_path_factory.mktemp("signal-run")
    pipeline.run(path)
    return path


def test_end_to_end_receipt_quality_and_separate_truth(completed):
    receipt = pipeline.verify_receipt(completed)
    assert receipt["status"] == "PASS"
    qa = json.loads((completed / "signal_quality.json").read_text())
    assert qa["raw_records"] == 2014 and qa["scheduled_buckets"] == 1008
    assert qa["blocked_monitor_buckets"] == 9 and qa["valid_zero_buckets"] == 1
    assert qa["reference_replay_equal"] and qa["total_failures"] == 0
    for name in [
        "synthetic_signal_records.csv",
        "signal_monitor.csv",
        "review_queue.csv",
        "reference.json",
    ]:
        assert "injected_event" not in (completed / name).read_text()
        assert "rate_anomaly" not in (completed / name).read_text()
    evaluation = json.loads((completed / "evaluation.json").read_text())
    assert evaluation["truth_used_by_detector"] is False
    assert (
        sum(evaluation["point_bucket_confusion"].values())
        == evaluation["admitted_monitor_buckets"]
    )


def test_repeat_run_keeps_data_and_scores_deterministic(completed, tmp_path):
    pipeline.run(tmp_path)
    for name in pipeline.DATA_ARTIFACTS:
        if name != "signal_monitor.duckdb":
            assert (completed / name).read_bytes() == (tmp_path / name).read_bytes()
    assert (completed / "manifest.json").read_bytes() == (
        tmp_path / "manifest.json"
    ).read_bytes()


def test_modified_or_incomplete_artifacts_fail_verification(completed, tmp_path):
    import shutil

    for name in (*pipeline.RECEIPT_ARTIFACTS, "run_receipt.json"):
        shutil.copyfile(completed / name, tmp_path / name)
    (tmp_path / "signal_monitor.csv").write_text("corrupted\n")
    with pytest.raises(ValueError, match="integrity"):
        pipeline.verify_receipt(tmp_path)
    receipt = json.loads((tmp_path / "run_receipt.json").read_text())
    receipt["artifacts"].pop("signal_monitor.csv")
    pipeline.write_json(tmp_path / "run_receipt.json", receipt)
    with pytest.raises(ValueError, match="incomplete"):
        pipeline.verify_receipt(tmp_path)


def test_failed_stage_preserves_previous_run_and_releases_lock(completed, monkeypatch):
    original = pipeline.verify_receipt(completed)

    def fail(stage, c):
        (stage / "signal_monitor.csv").write_text("partial")
        raise RuntimeError("simulated staging failure")

    with monkeypatch.context() as patch:
        patch.setattr(pipeline, "_stage", fail)
        with pytest.raises(RuntimeError, match="staging"):
            pipeline.run(completed)
    assert pipeline.verify_receipt(completed) == original
    assert not list(completed.glob(".stage-*"))
    with pipeline.lock_path(completed).open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(lock, fcntl.LOCK_UN)


def test_concurrent_writer_is_rejected(completed):
    with pipeline.lock_path(completed).open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            with pytest.raises(RuntimeError, match="already running"):
                pipeline.run(completed)
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


@pytest.mark.parametrize(
    "corruption",
    [
        "missing_queue",
        "missing_alert",
        "extra_alert",
        "duplicate_alert",
        "null_permission",
        "authorize_action",
        "review_status",
        "rank",
        "queue_residual",
        "point_flag",
        "change_flag",
        "change_direction",
        "cusum_up",
        "cusum_down",
        "null_state",
        "state_reset",
        "exposure_ratio",
        "rate",
        "policy_id",
        "quality_metadata",
    ],
)
def test_independent_checks_reject_false_passes(panel, tmp_path, corruption):
    c, rows = panel
    for row in rows:
        if row["event_day"] > c["baseline_end"]:
            row["complaints"] *= 2
    quality = inspect(rows, c)
    reference = fit_reference(rows, quality, c)
    scored = monitor(quality, reference, c)
    queue = build_review_queue(scored)
    assert len(queue) == 19
    if corruption == "missing_queue":
        queue = []
    elif corruption == "missing_alert":
        queue.pop()
    elif corruption in {"extra_alert", "duplicate_alert"}:
        extra = deepcopy(queue[0])
        if corruption == "extra_alert":
            extra["alert_id"] = "invented-alert"
        queue.append(extra)
    elif corruption in {"null_permission", "authorize_action"}:
        queue[0]["adverse_action_authorized"] = (
            None if corruption == "null_permission" else True
        )
    elif corruption in {"review_status", "rank", "queue_residual"}:
        field, value = {
            "review_status": ("review_status", "APPROVED"),
            "rank": ("queue_rank", 99),
            "queue_residual": ("standardized_residual", 0),
        }[corruption]
        queue[0][field] = value
    elif corruption == "quality_metadata":
        quality[0]["valid_zero"] = True
    else:
        field, value = {
            "point_flag": ("point_alert", False),
            "change_flag": ("change_alert", True),
            "change_direction": ("change_direction", "DOWN"),
            "cusum_up": ("cusum_up", 0),
            "cusum_down": ("cusum_down", 5),
            "null_state": ("cusum_up", None),
            "state_reset": ("state_reset", None),
            "exposure_ratio": ("exposure_ratio", 2),
            "rate": ("rate_per_1000", 999),
            "policy_id": ("policy_id", "invented-policy"),
        }[corruption]
        scored[0][field] = value
    with pytest.raises(ValueError, match="warehouse QA"):
        build(tmp_path / "bad.duckdb", rows, quality, reference, scored, queue)


@pytest.mark.parametrize(
    "field",
    ["rate", "dispersion", "mean_exposure", "baseline_input_sha256", "released_at"],
)
def test_rehashed_reference_cannot_override_raw_baseline(panel, tmp_path, field):
    import hashlib

    c, rows = panel
    quality = inspect(rows, c)
    reference = fit_reference(rows, quality, c)
    if field in {"rate", "dispersion", "mean_exposure"}:
        reference["rates"][0][field] *= 2
    else:
        reference[field] = (
            "0" * 64 if field == "baseline_input_sha256" else "2025-01-29T05:00:00Z"
        )
    material = {k: v for k, v in reference.items() if k != "reference_id"}
    reference["reference_id"] = (
        "signal-v1-"
        + hashlib.sha256(json.dumps(material, sort_keys=True).encode()).hexdigest()[:16]
    )
    scored = monitor(quality, reference, c)
    with pytest.raises(ValueError, match="warehouse QA"):
        build(
            tmp_path / "bad-reference.duckdb",
            rows,
            quality,
            reference,
            scored,
            build_review_queue(scored),
        )


@pytest.mark.parametrize(
    "scenario", ["downward", "recovery", "quality_gap", "row_order"]
)
def test_sql_cusum_matches_episode_and_gap_behavior(panel, tmp_path, scenario):
    import random

    c, rows = panel
    for row in rows:
        if c["baseline_end"] < row["event_day"] < "2025-02-05":
            row["complaints"] = 0 if scenario == "downward" else row["complaints"] * 2
        elif row["event_day"] >= "2025-02-10":
            row["complaints"] = 0
    if scenario == "quality_gap":
        rows = [r for r in rows if r["event_day"] != "2025-02-01"]
    elif scenario == "row_order":
        random.Random(19).shuffle(rows)
    quality = inspect(rows, c)
    reference = fit_reference(rows, quality, c)
    scored = monitor(quality, reference, c)
    result = build(
        tmp_path / "state.duckdb",
        rows,
        quality,
        reference,
        scored,
        build_review_queue(scored),
    )
    assert result["checks"]["independent_cusum_state"] == 0
    directions = [r["change_direction"] for r in scored if r["change_alert"]]
    assert directions == (
        ["DOWN", "DOWN"]
        if scenario == "downward"
        else ["DOWN"]
        if scenario == "quality_gap"
        else ["UP", "DOWN"]
    )


@pytest.mark.parametrize(
    "artifact",
    [
        "signal_monitor.csv",
        "reference.json",
        "manifest.json",
        "evaluation.json",
        "signal_quality.json",
        "signal_monitor.duckdb",
    ],
)
def test_rehashed_artifact_still_fails_semantic_verification(
    completed, tmp_path, artifact
):
    shutil.copytree(completed, tmp_path / "copy")
    output = tmp_path / "copy"
    path = output / artifact
    if artifact == "signal_monitor.csv":
        path.write_bytes(path.read_bytes().replace(b",False,", b",True,", 1))
    elif artifact == "signal_monitor.duckdb":
        with duckdb.connect(str(path)) as con:
            con.execute("DELETE FROM signal_review")
    else:
        data = json.loads(path.read_text())
        if artifact == "reference.json":
            data["rates"][0]["dispersion"] *= 2
        elif artifact == "manifest.json":
            data["source_sha256"]["signal_demo/detection.py"] = "0" * 64
        elif artifact == "evaluation.json":
            data["point_bucket_confusion"]["false_negative"] = 0
        else:
            data["total_failures"] = 1
        pipeline.write_json(path, data)
    receipt = json.loads((output / "run_receipt.json").read_text())
    receipt["artifacts"][artifact] = pipeline.digest(path)
    pipeline.write_json(output / "run_receipt.json", receipt)
    with pytest.raises(ValueError, match="mismatch"):
        pipeline.verify_receipt(output)


@pytest.mark.parametrize(
    "field,value",
    [
        ("unsigned", False),
        ("authenticity_established", True),
        ("boundary", "production accuracy proven"),
        ("checks", {"python_sql_parity": 1, "reference_replay_equal": True}),
    ],
)
def test_receipt_cannot_claim_authenticity_or_wider_scope(
    completed, tmp_path, field, value
):
    output = tmp_path / "copy"
    shutil.copytree(completed, output)
    receipt = json.loads((output / "run_receipt.json").read_text())
    receipt[field] = value
    pipeline.write_json(output / "run_receipt.json", receipt)
    with pytest.raises(ValueError, match="receipt contract"):
        pipeline.verify_receipt(output)


def test_current_source_must_match_manifest(completed, monkeypatch):
    manifest = pipeline.make_manifest

    def changed(c, reference):
        result = manifest(c, reference)
        result["source_sha256"]["signal_demo/detection.py"] = "f" * 64
        return result

    monkeypatch.setattr(pipeline, "make_manifest", changed)
    with pytest.raises(ValueError, match="manifest mismatch"):
        pipeline.verify_receipt(completed)


def test_publish_rename_failure_restores_completed_run(completed, monkeypatch):
    original = {p.name: p.read_bytes() for p in completed.iterdir()}
    rename = Path.rename

    def fail_publish(path, target):
        if path.name.startswith(".stage-") and target == completed:
            raise OSError("simulated publication failure")
        return rename(path, target)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "rename", fail_publish)
        with pytest.raises(OSError, match="publication"):
            pipeline.run(completed)
    assert {p.name: p.read_bytes() for p in completed.iterdir()} == original
    assert not list(completed.parent.glob(".stage-*"))
    assert not list(completed.parent.glob(".backup-*"))


def test_unknown_output_and_symlink_are_preserved(tmp_path):
    output = tmp_path / "unrelated"
    output.mkdir()
    (output / "keep.txt").write_text("user-owned contents")
    with pytest.raises(ValueError, match="unrecognized"):
        pipeline.run(output)
    assert (output / "keep.txt").read_text() == "user-owned contents"
    alias = tmp_path / "alias"
    alias.symlink_to(output, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        pipeline.run(alias)


def test_writer_alias_cannot_bypass_stable_lock(completed, tmp_path):
    alias = tmp_path / "parent-alias"
    alias.symlink_to(completed.parent, target_is_directory=True)
    with pipeline.lock_path(completed).open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            with pytest.raises(RuntimeError, match="already running"):
                pipeline.run(alias / completed.name)
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def test_database_replay_does_not_require_undeclared_timezone_package(completed):
    code = """
import importlib.abc
import sys
class NoPytz(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'pytz' or fullname.startswith('pytz.'):
            raise ImportError('undeclared timezone package prohibited')
sys.meta_path.insert(0, NoPytz())
from signal_demo.receipts import database_fingerprint
assert len(database_fingerprint(sys.argv[1])) == 64
"""
    subprocess.run(
        [sys.executable, "-c", code, str(completed / "signal_monitor.duckdb")],
        check=True,
    )
