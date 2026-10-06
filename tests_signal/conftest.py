from datetime import date, datetime, timedelta, timezone

import pytest

from signal_demo.contracts import calendar, iso, load_contract


@pytest.fixture
def panel():
    c = load_contract()
    c.update(areas=["SYN000"], end_day="2025-02-15", baseline_end="2025-01-28")
    rows = []
    for day in calendar(c):
        for channel, count in [("mobile", 10), ("legacy", 6)]:
            rows.append(
                {
                    "record_id": f"OBS{len(rows):06d}",
                    "area_id": "SYN000",
                    "event_day": day,
                    "channel": channel,
                    "complaints": count,
                    "opportunities": 500,
                    "available_at": iso(
                        datetime.combine(
                            date.fromisoformat(day) + timedelta(days=1),
                            datetime.min.time(),
                            timezone.utc,
                        )
                        + timedelta(hours=6)
                    ),
                    "complete": True,
                    "synthetic_record": True,
                }
            )
    return c, rows
