from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import json
import math
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
FIELDS = {
    "record_id", "area_id", "event_day", "channel", "complaints",
    "opportunities", "available_at", "complete", "synthetic_record",
}


def utc(value: str) -> datetime:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value):
        raise ValueError("canonical UTC timestamp required")
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_contract(path: Path | None = None) -> dict:
    c = json.loads((path or ROOT / "contracts/signal_contract.json").read_text())
    for key, expected in {
        "synthetic_only": True, "scientific_results_claimed": False,
        "real_complaint_data_used": False,
    }.items():
        if c.get(key) is not expected:
            raise ValueError("synthetic claim contract violated")
    if c.get("version") != "1.0" or c.get("channels") != ["mobile", "legacy"]:
        raise ValueError("unsupported schema")
    areas = c["areas"]
    if not areas or len(areas) != len(set(areas)) or any(not re.fullmatch(r"SYN\d{3}", a) for a in areas):
        raise ValueError("invalid fabricated area inventory")
    start, end, baseline = (date.fromisoformat(c[k]) for k in ["start_day", "end_day", "baseline_end"])
    if not start <= baseline < end:
        raise ValueError("invalid baseline/monitor dates")
    for key in ["min_baseline_days", "min_baseline_events", "min_shift_streak", "recovery_days"]:
        if type(c[key]) is not int or c[key] <= 0:
            raise ValueError("positive integer policy parameters required")
    if c["min_baseline_days"] < 2 or type(c["seed"]) is not int or c["seed"] < 0:
        raise ValueError("at least two baseline days and a non-negative integer seed required")
    for key in ["point_limit", "cusum_k", "cusum_h", "cusum_clip", "max_latency_hours"]:
        if isinstance(c[key], bool) or not isinstance(c[key], (int, float)) or not math.isfinite(c[key]) or c[key] <= 0:
            raise ValueError("finite positive detector parameters required")
    if type(c["monitor_hour_next_day"]) is not int or not 0 <= c["monitor_hour_next_day"] <= 23:
        raise ValueError("invalid monitoring hour")
    return c


def calendar(c: dict):
    day, end = date.fromisoformat(c["start_day"]), date.fromisoformat(c["end_day"])
    while day <= end:
        yield day.isoformat()
        day += timedelta(days=1)


def monitor_at(day: str, c: dict) -> datetime:
    return datetime.combine(date.fromisoformat(day) + timedelta(days=1), datetime.min.time(), timezone.utc) + timedelta(hours=c["monitor_hour_next_day"])


def validate_records(rows: list[dict], c: dict) -> None:
    if not isinstance(rows, list) or not rows:
        raise ValueError("non-empty record list required")
    ids = set()
    for row in rows:
        if set(row) != FIELDS:
            raise ValueError("record schema mismatch; labels and unknown fields are not admitted")
        identity = row["record_id"]
        if not isinstance(identity, str) or not re.fullmatch(r"OBS\d{6}", identity) or identity in ids:
            raise ValueError("invalid/duplicate record identity")
        ids.add(identity)
        if row["area_id"] not in c["areas"] or row["channel"] not in c["channels"]:
            raise ValueError("unexpected area/channel")
        day = row["event_day"]
        if not isinstance(day, str) or date.fromisoformat(day).isoformat() != day or not c["start_day"] <= day <= c["end_day"]:
            raise ValueError("invalid observation day")
        for key in ["complaints", "opportunities"]:
            if type(row[key]) is not int or row[key] < 0:
                raise ValueError("non-negative integer counts/exposures required")
        if type(row["complete"]) is not bool or row["synthetic_record"] is not True:
            raise ValueError("boolean completeness and synthetic markers required")
        period_end = datetime.combine(date.fromisoformat(day) + timedelta(days=1), datetime.min.time(), timezone.utc)
        if utc(row["available_at"]) < period_end:
            raise ValueError("completed-day signal cannot be available before period end")
