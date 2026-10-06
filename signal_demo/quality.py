from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone

from .contracts import calendar, iso, monitor_at, utc, validate_records


def inspect(rows: list[dict], c: dict) -> list[dict]:
    validate_records(rows, c)
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["area_id"], row["event_day"]].append(row)
    panel = []
    for area in c["areas"]:
        for day in calendar(c):
            records = grouped[area, day]
            counts = Counter(r["channel"] for r in records)
            reasons = []
            if set(counts) != set(c["channels"]):
                reasons.append("MISSING_CHANNEL")
            if any(n > 1 for n in counts.values()):
                reasons.append("DUPLICATE_CHANNEL")
            if any(not r["complete"] for r in records):
                reasons.append("INCOMPLETE_BATCH")
            if any(r["opportunities"] == 0 for r in records):
                reasons.append("ZERO_EXPOSURE")
            asof = monitor_at(day, c)
            period_end = datetime.combine(
                date.fromisoformat(day) + timedelta(days=1),
                datetime.min.time(),
                timezone.utc,
            )
            if any(utc(r["available_at"]) > asof for r in records):
                reasons.append("UNAVAILABLE_AT_MONITOR")
            if any(
                (utc(r["available_at"]) - period_end).total_seconds()
                > c["max_latency_hours"] * 3600
                for r in records
            ):
                reasons.append("LATE_BATCH")
            admitted = not reasons
            item = {
                "area_id": area,
                "event_day": day,
                "monitor_at": iso(asof),
                "admitted": admitted,
                "quality_status": "ADMITTED" if admitted else "BLOCKED",
                "reason_codes": json.dumps(sorted(reasons), separators=(",", ":")),
                "complaints": sum(r["complaints"] for r in records)
                if admitted
                else None,
                "opportunities": sum(r["opportunities"] for r in records)
                if admitted
                else None,
                "valid_zero": admitted and all(r["complaints"] == 0 for r in records),
            }
            for channel in c["channels"]:
                matching = [r for r in records if r["channel"] == channel]
                item[channel + "_complaints"] = (
                    matching[0]["complaints"] if admitted else None
                )
                item[channel + "_opportunities"] = (
                    matching[0]["opportunities"] if admitted else None
                )
            panel.append(item)
    return panel
