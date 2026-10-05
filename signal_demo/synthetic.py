from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import numpy as np

from .contracts import calendar, iso


def generate(c: dict) -> tuple[list[dict], list[dict]]:
    """Truth is separate from every operational record."""
    rng = np.random.default_rng(c["seed"])
    rows, truth = [], []
    for day_index, day in enumerate(calendar(c)):
        for area_index, area in enumerate(c["areas"]):
            injected = "NONE"
            if area_index == 1 and day_index == 96:
                injected = "POINT_SPIKE"
            elif area_index == 2 and day_index >= 84:
                injected = "RATE_SHIFT"
            elif area_index == 3 and day_index >= 77:
                injected = "ACCESS_CHANGE"
            elif area_index == 4 and 100 <= day_index <= 102:
                injected = "MISSING_CHANNEL"
            elif area_index == 5 and 107 <= day_index <= 109:
                injected = "LATE_DATA"
            elif area_index == 5 and day_index == 116:
                injected = "ZERO_EXPOSURE"
            elif area_index == 5 and day_index == 118:
                injected = "ZERO_REPORTS"
            elif area_index == 5 and day_index == 121:
                injected = "DUPLICATE_CHANNEL"
            elif area_index == 4 and day_index == 117:
                injected = "INCOMPLETE_BATCH"
            truth.append({
                "area_id": area, "event_day": day, "injected_event": injected,
                "rate_anomaly": injected in {"POINT_SPIKE", "RATE_SHIFT", "ZERO_REPORTS"},
            })
            for channel in c["channels"]:
                if injected == "MISSING_CHANNEL" and channel == "legacy":
                    continue
                opportunities = 500 + int(rng.integers(-40, 41))
                if injected == "ACCESS_CHANGE" and channel == "mobile":
                    opportunities *= 4
                rate = 0.025 if channel == "mobile" else 0.015
                if injected == "RATE_SHIFT":
                    rate *= 2
                count = int(rng.poisson(opportunities * rate))
                if injected == "POINT_SPIKE" and channel == "mobile":
                    count += 90
                if injected == "ZERO_REPORTS":
                    count = 0
                if injected == "ZERO_EXPOSURE" and channel == "mobile":
                    opportunities, count = 0, 0
                availability = datetime.combine(date.fromisoformat(day)+timedelta(days=1), datetime.min.time(), timezone.utc) + timedelta(hours=6)
                if injected == "LATE_DATA":
                    availability += timedelta(hours=24)
                row = {
                    "record_id": f"OBS{len(rows):06d}", "area_id": area,
                    "event_day": day, "channel": channel, "complaints": count,
                    "opportunities": opportunities, "available_at": iso(availability),
                    "complete": injected != "INCOMPLETE_BATCH", "synthetic_record": True,
                }
                rows.append(row)
                if injected == "DUPLICATE_CHANNEL" and channel == "mobile":
                    rows.append({**row, "record_id": f"OBS{len(rows):06d}"})
    return rows, truth
