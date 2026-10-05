import fcntl
import json

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
    assert qa["status"] == "PASS" and len(qa["checks"]) == 10 and not any(qa["checks"].values())
    with duckdb.connect(str(path), read_only=True) as con:
        assert con.execute("SELECT MIN(expected_count),MAX(expected_count) FROM mart.signal_expectation").fetchone() == (16.0, 16.0)
        assert con.execute("SELECT COUNT(*) FROM mart.signal_coverage").fetchone()[0] == 46


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
    for name in ["synthetic_signal_records.csv", "signal_monitor.csv", "review_queue.csv", "reference.json"]:
        assert "injected_event" not in (completed / name).read_text()
        assert "rate_anomaly" not in (completed / name).read_text()
    evaluation = json.loads((completed / "evaluation.json").read_text())
    assert evaluation["truth_used_by_detector"] is False
    assert sum(evaluation["point_bucket_confusion"].values()) == evaluation["admitted_monitor_buckets"]


def test_repeat_run_keeps_data_and_scores_deterministic(completed, tmp_path):
    pipeline.run(tmp_path)
    for name in pipeline.DATA_ARTIFACTS:
        if name != "signal_monitor.duckdb":
            assert (completed / name).read_bytes() == (tmp_path / name).read_bytes()
    assert (completed / "manifest.json").read_bytes() == (tmp_path / "manifest.json").read_bytes()


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
    with (completed / ".signal_demo.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(lock, fcntl.LOCK_UN)


def test_concurrent_writer_is_rejected(completed):
    with (completed / ".signal_demo.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            with pytest.raises(RuntimeError, match="already running"):
                pipeline.run(completed)
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)
