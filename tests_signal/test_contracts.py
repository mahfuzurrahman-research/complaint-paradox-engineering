import json
from datetime import datetime, timezone

import pytest

from signal_demo import pipeline
from signal_demo.contracts import (
    iso,
    load_contract,
    strict_json,
    validate_contract,
    validate_records,
)
from signal_demo.detection import fit_reference, monitor
from signal_demo.quality import inspect
from signal_demo.receipts import load_raw


@pytest.mark.parametrize(
    "field,value",
    [
        ("areas", []),
        ("areas", ["SYN000", "SYN000"]),
        ("areas", [123]),
        ("start_day", "20250101"),
        ("end_day", "9999-12-31"),
        ("baseline_end", "2025-06-17"),
        ("min_baseline_days", True),
        ("point_limit", float("inf")),
        ("cusum_clip", 0.5),
        ("policy_id", " synthetic-signal-v1"),
        ("synthetic_only", 1),
        ("extra", "unknown"),
    ],
)
def test_invalid_policy_is_rejected(field, value):
    c = load_contract()
    c[field] = value
    with pytest.raises(ValueError):
        validate_contract(c)


@pytest.mark.parametrize(
    "payload",
    [
        '{"policy_id":"a","policy_id":"b"}',
        '{"x":NaN}',
        '{"x":Infinity}',
        '{"x":-Infinity}',
    ],
)
def test_ambiguous_or_nonfinite_json_is_rejected(payload):
    with pytest.raises(ValueError):
        strict_json(payload)


def test_policy_file_requires_complete_schema(tmp_path):
    c = load_contract()
    c.pop("point_limit")
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(c))
    with pytest.raises(ValueError, match="schema"):
        load_contract(path)


def test_large_counts_fail_before_database_cast(panel):
    c, rows = panel
    rows[0]["complaints"] = 2**31
    with pytest.raises(ValueError, match="bounded"):
        validate_records(rows, c)


def test_forged_quality_cannot_fit_reference(panel):
    c, rows = panel
    quality = inspect(rows, c)
    quality[0]["mobile_complaints"] *= 10
    with pytest.raises(ValueError, match="reconstruction"):
        fit_reference(rows, quality, c)


@pytest.mark.parametrize(
    "corruption", ["missing_rate", "duplicate_rate", "nan_rate", "wrong_fingerprint"]
)
def test_reference_inventory_and_fingerprint_are_enforced(panel, corruption):
    c, rows = panel
    quality = inspect(rows, c)
    reference = fit_reference(rows, quality, c)
    if corruption == "missing_rate":
        reference["rates"].pop()
    elif corruption == "duplicate_rate":
        reference["rates"].append(reference["rates"][0].copy())
    elif corruption == "nan_rate":
        reference["rates"][0]["rate"] = float("nan")
    else:
        reference["reference_id"] = "signal-v1-" + "0" * 16
    with pytest.raises(ValueError, match="inventory|quantities|fingerprint"):
        monitor(quality, reference, c)


@pytest.mark.parametrize(
    "corruption", ["duplicate_header", "ragged", "boolean", "padded_count"]
)
def test_raw_csv_contract_is_checked_before_replay(panel, tmp_path, corruption):
    c, rows = panel
    path = tmp_path / "raw.csv"
    pipeline.write_csv(path, rows)
    text = path.read_text()
    if corruption == "duplicate_header":
        text = text.replace("record_id,area_id", "record_id,record_id", 1)
    elif corruption == "ragged":
        lines = text.splitlines()
        lines[1] += ",extra"
        text = "\n".join(lines) + "\n"
    elif corruption == "boolean":
        text = text.replace(",True,True", ",1,True", 1)
    else:
        text = text.replace(",10,500,", ", 10,500,", 1)
    path.write_text(text)
    with pytest.raises(ValueError):
        load_raw(path, c)


def test_whole_second_utc_serialization_supports_early_years():
    assert iso(datetime(1, 1, 1, tzinfo=timezone.utc)) == "0001-01-01T00:00:00Z"
    with pytest.raises(ValueError, match="aware"):
        iso(datetime(2025, 1, 1))
