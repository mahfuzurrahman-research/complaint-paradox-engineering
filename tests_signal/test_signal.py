from copy import deepcopy
import math
import random

import pytest

from signal_demo.contracts import validate_records
from signal_demo.detection import Cusum, build_review_queue, fit_reference, monitor
from signal_demo.quality import inspect


def detect(c, rows):
    quality = inspect(rows, c)
    reference = fit_reference(rows, quality, c)
    return quality, reference, monitor(quality, reference, c)


@pytest.mark.parametrize("field,value", [
    ("complaints", -1), ("complaints", True), ("complaints", 1.5),
    ("complaints", float("nan")), ("complaints", "4"),
    ("opportunities", -1), ("opportunities", False), ("opportunities", float("inf")),
])
def test_invalid_counts_are_rejected(panel, field, value):
    c, rows = panel
    rows[0][field] = value
    with pytest.raises(ValueError, match="integer"):
        validate_records(rows, c)


def test_truth_fields_and_reused_ids_are_rejected(panel):
    c, rows = panel
    tagged = deepcopy(rows)
    tagged[0]["injected_event"] = "NONE"
    with pytest.raises(ValueError, match="schema"):
        validate_records(tagged, c)
    rows[1]["record_id"] = rows[0]["record_id"]
    with pytest.raises(ValueError, match="identity"):
        validate_records(rows, c)


def test_completed_period_cannot_be_available_in_advance(panel):
    c, rows = panel
    rows[0]["available_at"] = "2025-01-01T23:59:59Z"
    with pytest.raises(ValueError, match="period end"):
        validate_records(rows, c)


@pytest.mark.parametrize("failure,reason", [
    ("missing", "MISSING_CHANNEL"), ("duplicate", "DUPLICATE_CHANNEL"),
    ("incomplete", "INCOMPLETE_BATCH"), ("zero_exposure", "ZERO_EXPOSURE"),
    ("future", "UNAVAILABLE_AT_MONITOR"), ("late", "LATE_BATCH"),
])
def test_bad_bucket_is_blocked_without_zero_imputation(panel, failure, reason):
    c, rows = panel
    record = next(r for r in rows if r["event_day"] == "2025-02-01")
    if failure == "missing":
        rows.remove(record)
    elif failure == "duplicate":
        rows.append({**record, "record_id": "OBS900000"})
    elif failure == "incomplete":
        record["complete"] = False
    elif failure == "zero_exposure":
        record["opportunities"] = 0
    elif failure == "future":
        record["available_at"] = "2025-02-02T08:00:00Z"
    else:
        record["available_at"] = "2025-02-03T06:00:00Z"
    _, _, scored = detect(c, rows)
    bucket = next(s for s in scored if s["event_day"] == "2025-02-01")
    assert reason in bucket["reason_codes"]
    assert bucket["complaints"] is None and bucket["standardized_residual"] is None
    assert not bucket["admitted"] and not bucket["valid_zero"]
    assert bucket["state_reset"] and not bucket["point_alert"] and not bucket["change_alert"]
    queue = build_review_queue(scored)
    assert len(queue) == 1 and queue[0]["recommended_action"] == "CHECK_FEED"


def test_whole_missing_day_remains_scheduled(panel):
    c, rows = panel
    rows = [r for r in rows if r["event_day"] != "2025-02-01"]
    quality, _, scored = detect(c, rows)
    assert len(quality) == 46 and len(scored) == 18
    missing = next(s for s in scored if s["event_day"] == "2025-02-01")
    assert not missing["admitted"] and missing["opportunities"] is None


def test_real_zero_is_admitted_and_can_trigger_point_alert(panel):
    c, rows = panel
    for r in rows:
        if r["event_day"] == "2025-02-01":
            r["complaints"] = 0
    _, _, scored = detect(c, rows)
    zero = next(s for s in scored if s["event_day"] == "2025-02-01")
    assert zero["admitted"] and zero["valid_zero"]
    assert zero["standardized_residual"] == -4 and zero["point_alert"]
    assert not zero["change_alert"]


@pytest.mark.parametrize("case", ["incomplete", "history", "events"])
def test_unusable_baseline_prevents_monitoring(panel, case):
    c, rows = panel
    if case == "incomplete":
        rows[0]["complete"] = False
    elif case == "history":
        c["min_baseline_days"] = 29
    else:
        c["min_baseline_events"] = 100000
    with pytest.raises(ValueError, match="baseline"):
        detect(c, rows)


def test_future_observations_cannot_change_reference_or_earlier_alerts(panel):
    c, rows = panel
    _, reference, scored = detect(c, rows)
    changed = deepcopy(rows)
    for row in changed:
        if row["event_day"] >= "2025-02-10":
            row["complaints"] *= 9
    _, new_reference, new_scored = detect(c, changed)
    assert new_reference == reference
    assert [s for s in scored if s["event_day"] < "2025-02-10"] == [s for s in new_scored if s["event_day"] < "2025-02-10"]


def test_row_order_does_not_change_reference_scores_or_queue(panel):
    c, rows = panel
    expected = detect(c, rows)
    random.Random(44).shuffle(rows)
    actual = detect(c, rows)
    assert actual == expected
    assert build_review_queue(actual[2]) == build_review_queue(expected[2])


def test_reference_must_be_available_and_policy_frozen(panel):
    c, rows = panel
    quality, reference, _ = detect(c, rows)
    changed_policy = {**c, "point_limit": 2}
    with pytest.raises(ValueError, match="policy mismatch"):
        monitor(quality, reference, changed_policy)
    reference["released_at"] = "2025-02-01T08:00:00Z"
    with pytest.raises(ValueError, match="unavailable"):
        monitor(quality, reference, c)


def test_channel_access_growth_at_unchanged_rate_is_not_anomaly(panel):
    c, rows = panel
    for row in rows:
        if row["event_day"] > c["baseline_end"] and row["channel"] == "mobile":
            row["opportunities"] *= 4
            row["complaints"] *= 4
    _, _, scored = detect(c, rows)
    assert all(s["complaints"] == 46 and s["expected_count"] == 46 for s in scored)
    assert all(s["exposure_ratio"] == 2.5 and s["standardized_residual"] == 0 for s in scored)
    assert build_review_queue(scored) == []


def test_isolated_spike_and_sustained_shift_have_different_alerts(panel):
    c, rows = panel
    spike = deepcopy(rows)
    next(r for r in spike if r["event_day"] == "2025-01-29")["complaints"] = 100
    _, _, scored = detect(c, spike)
    assert sum(s["point_alert"] for s in scored) == 1
    assert not any(s["change_alert"] for s in scored)
    for row in rows:
        if row["event_day"] > c["baseline_end"]:
            row["complaints"] *= 2
    _, _, shifted = detect(c, rows)
    changes = [s for s in shifted if s["change_alert"]]
    assert len(changes) == 1 and changes[0]["event_day"] == "2025-02-01"
    assert changes[0]["change_direction"] == "UP"
    assert all(s["point_alert"] for s in shifted)


def test_quality_gap_resets_accumulation(panel):
    c, rows = panel
    for r in rows:
        if r["event_day"] in {"2025-01-29", "2025-01-30", "2025-01-31", "2025-02-02", "2025-02-03", "2025-02-04"}:
            r["complaints"] *= 2
    rows = [r for r in rows if r["event_day"] != "2025-02-01"]
    _, _, scored = detect(c, rows)
    assert not any(s["change_alert"] for s in scored)
    gap = next(s for s in scored if s["event_day"] == "2025-02-01")
    assert gap["cusum_up"] == gap["cusum_down"] == 0


def test_cusum_downward_detection_latch_and_recovery(panel):
    c, _ = panel
    state = Cusum()
    assert [state.update(-3, c) for _ in range(4)] == [None, None, None, "DOWN"]
    assert all(state.update(-3, c) is None for _ in range(12))
    for _ in range(c["recovery_days"]):
        assert state.update(0, c) is None
    assert state.latched is None and state.down == 0
    assert [state.update(3, c) for _ in range(4)] == [None, None, None, "UP"]
    with pytest.raises(ValueError, match="finite"):
        state.update(math.nan, c)


def test_queue_contains_no_truth_or_permission_for_adverse_action(panel):
    c, rows = panel
    for r in rows:
        if r["event_day"] > c["baseline_end"]:
            r["complaints"] *= 2
    _, _, scored = detect(c, rows)
    queue = build_review_queue(scored)
    assert queue[0]["alert_type"] == "RATE_SHIFT_ALERT"
    assert len({q["alert_id"] for q in queue}) == len(queue)
    assert all(q["review_status"] == "PENDING_REVIEW" and q["adverse_action_authorized"] is False for q in queue)
    assert all("injected_event" not in q and "rate_anomaly" not in q for q in queue)
