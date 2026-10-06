from __future__ import annotations

import json
import math
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIELDS = {
    "record_id",
    "area_id",
    "event_day",
    "channel",
    "complaints",
    "opportunities",
    "available_at",
    "complete",
    "synthetic_record",
}

POLICY_FIELDS = {
    "version",
    "policy_id",
    "synthetic_only",
    "scientific_results_claimed",
    "real_complaint_data_used",
    "areas",
    "channels",
    "start_day",
    "end_day",
    "baseline_end",
    "monitor_hour_next_day",
    "max_latency_hours",
    "min_baseline_days",
    "min_baseline_events",
    "point_limit",
    "cusum_k",
    "cusum_h",
    "cusum_clip",
    "min_shift_streak",
    "recovery_days",
    "seed",
    "exposure_unit",
    "rate_meaning",
}


def strict_json(text: str):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    def constant(value):
        raise ValueError(f"nonfinite JSON constant: {value}")

    return json.loads(text, object_pairs_hook=pairs, parse_constant=constant)


def utc(value: str) -> datetime:
    if not isinstance(value, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value
    ):
        raise ValueError("canonical UTC timestamp required")
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def iso(value: datetime) -> str:
    if value.tzinfo is None or value.microsecond:
        raise ValueError("aware whole-second datetime required")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def load_contract(path: Path | None = None) -> dict:
    return validate_contract(
        strict_json((path or ROOT / "contracts/signal_contract.json").read_text())
    )


def validate_contract(c: dict) -> dict:
    if not isinstance(c, dict) or set(c) != POLICY_FIELDS:
        raise ValueError("exact signal policy schema required")
    for key in ("policy_id", "exposure_unit", "rate_meaning"):
        if not isinstance(c[key], str) or not c[key] or c[key] != c[key].strip():
            raise ValueError("nonblank unpadded policy text required")
    for key, expected in {
        "synthetic_only": True,
        "scientific_results_claimed": False,
        "real_complaint_data_used": False,
    }.items():
        if c.get(key) is not expected:
            raise ValueError("synthetic claim contract violated")
    if c.get("version") != "1.0" or c.get("channels") != ["mobile", "legacy"]:
        raise ValueError("unsupported schema")
    areas = c["areas"]
    if (
        not isinstance(areas, list)
        or not areas
        or any(
            not isinstance(a, str) or not re.fullmatch(r"SYN\d{3}", a) for a in areas
        )
        or len(areas) != len(set(areas))
    ):
        raise ValueError("invalid fabricated area inventory")
    for key in ("start_day", "end_day", "baseline_end"):
        if (
            not isinstance(c[key], str)
            or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", c[key])
            or date.fromisoformat(c[key]).isoformat() != c[key]
        ):
            raise ValueError("canonical policy date required")
    start, end, baseline = (
        date.fromisoformat(c[k]) for k in ["start_day", "end_day", "baseline_end"]
    )
    if not start <= baseline < end or end == date.max:
        raise ValueError("invalid baseline/monitor dates")
    for key in [
        "min_baseline_days",
        "min_baseline_events",
        "min_shift_streak",
        "recovery_days",
    ]:
        if type(c[key]) is not int or c[key] <= 0:
            raise ValueError("positive integer policy parameters required")
    if c["min_baseline_days"] < 2 or type(c["seed"]) is not int or c["seed"] < 0:
        raise ValueError(
            "at least two baseline days and a non-negative integer seed required"
        )
    for key in ["point_limit", "cusum_k", "cusum_h", "cusum_clip", "max_latency_hours"]:
        if (
            isinstance(c[key], bool)
            or not isinstance(c[key], (int, float))
            or not math.isfinite(c[key])
            or c[key] <= 0
        ):
            raise ValueError("finite positive detector parameters required")
    if (
        type(c["monitor_hour_next_day"]) is not int
        or not 0 <= c["monitor_hour_next_day"] <= 23
    ):
        raise ValueError("invalid monitoring hour")
    if c["cusum_clip"] <= c["cusum_k"]:
        raise ValueError("CUSUM clipping must exceed drift allowance")
    return c


def calendar(c: dict):
    day, end = date.fromisoformat(c["start_day"]), date.fromisoformat(c["end_day"])
    while day <= end:
        yield day.isoformat()
        day += timedelta(days=1)


def monitor_at(day: str, c: dict) -> datetime:
    return datetime.combine(
        date.fromisoformat(day) + timedelta(days=1), datetime.min.time(), timezone.utc
    ) + timedelta(hours=c["monitor_hour_next_day"])


def validate_records(rows: list[dict], c: dict) -> None:
    validate_contract(c)
    if not isinstance(rows, list) or not rows:
        raise ValueError("non-empty record list required")
    ids = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != FIELDS:
            raise ValueError(
                "record schema mismatch; labels and unknown fields are not admitted"
            )
        identity = row["record_id"]
        if (
            not isinstance(identity, str)
            or not re.fullmatch(r"OBS\d{6}", identity)
            or identity in ids
        ):
            raise ValueError("invalid/duplicate record identity")
        ids.add(identity)
        if row["area_id"] not in c["areas"] or row["channel"] not in c["channels"]:
            raise ValueError("unexpected area/channel")
        day = row["event_day"]
        if (
            not isinstance(day, str)
            or date.fromisoformat(day).isoformat() != day
            or not c["start_day"] <= day <= c["end_day"]
        ):
            raise ValueError("invalid observation day")
        for key in ["complaints", "opportunities"]:
            if type(row[key]) is not int or not 0 <= row[key] <= 2**31 - 1:
                raise ValueError(
                    "bounded non-negative integer counts/exposures required"
                )
        if type(row["complete"]) is not bool or row["synthetic_record"] is not True:
            raise ValueError("boolean completeness and synthetic markers required")
        period_end = datetime.combine(
            date.fromisoformat(day) + timedelta(days=1),
            datetime.min.time(),
            timezone.utc,
        )
        if utc(row["available_at"]) < period_end:
            raise ValueError(
                "completed-day signal cannot be available before period end"
            )
