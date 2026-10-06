from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from statistics import mean, stdev

from .contracts import utc, validate_contract


def fit_reference(rows: list[dict], quality: list[dict], c: dict) -> dict:
    from .quality import inspect

    if quality != inspect(rows, c):
        raise ValueError("quality panel differs from raw input reconstruction")
    baseline = [q for q in quality if q["event_day"] <= c["baseline_end"]]
    if not baseline or any(not q["admitted"] for q in baseline):
        raise ValueError("complete admitted baseline required")
    reference = {
        "version": c["version"],
        "policy_id": c["policy_id"],
        "policy": json.loads(json.dumps(c)),
        "baseline_start": c["start_day"],
        "baseline_end": c["baseline_end"],
        "rates": [],
        "raw_count_baseline": {},
    }
    for area in c["areas"]:
        days = [q for q in baseline if q["area_id"] == area]
        if len(days) < c["min_baseline_days"]:
            raise ValueError("insufficient baseline days")
        for channel in c["channels"]:
            y = [q[channel + "_complaints"] for q in days]
            e = [q[channel + "_opportunities"] for q in days]
            if sum(y) < c["min_baseline_events"]:
                raise ValueError("insufficient baseline event mass")
            rate = sum(y) / sum(e)
            phi = max(
                1.0,
                sum((v - rate * x) ** 2 / max(rate * x, 1.0) for v, x in zip(y, e))
                / (len(y) - 1),
            )
            reference["rates"].append(
                {
                    "area_id": area,
                    "channel": channel,
                    "rate": rate,
                    "dispersion": phi,
                    "mean_exposure": mean(e),
                    "baseline_days": len(days),
                }
            )
        raw = [q["complaints"] for q in days]
        reference["raw_count_baseline"][area] = {
            "mean": mean(raw),
            "sd": max(stdev(raw), 1.0),
        }
    baseline_rows = sorted(
        [r for r in rows if r["event_day"] <= c["baseline_end"]],
        key=lambda r: (r["area_id"], r["event_day"], r["channel"], r["record_id"]),
    )
    reference["released_at"] = max(r["available_at"] for r in baseline_rows)
    reference["baseline_input_sha256"] = hashlib.sha256(
        json.dumps(baseline_rows, sort_keys=True).encode()
    ).hexdigest()
    reference["reference_id"] = (
        "signal-v1-"
        + hashlib.sha256(
            json.dumps(reference, sort_keys=True, allow_nan=False).encode()
        ).hexdigest()[:16]
    )
    return reference


def validate_reference(reference: dict, c: dict) -> None:
    validate_contract(c)
    fields = {
        "version",
        "policy_id",
        "policy",
        "baseline_start",
        "baseline_end",
        "rates",
        "raw_count_baseline",
        "released_at",
        "baseline_input_sha256",
        "reference_id",
    }
    if not isinstance(reference, dict) or set(reference) != fields:
        raise ValueError("reference schema mismatch")
    if (
        reference["policy"] != c
        or reference["policy_id"] != c["policy_id"]
        or reference["version"] != c["version"]
        or reference["baseline_start"] != c["start_day"]
        or reference["baseline_end"] != c["baseline_end"]
    ):
        raise ValueError("frozen reference/policy mismatch")
    utc(reference["released_at"])
    import re

    if not isinstance(reference["baseline_input_sha256"], str) or not re.fullmatch(
        r"[a-f0-9]{64}", reference["baseline_input_sha256"]
    ):
        raise ValueError("invalid baseline input fingerprint")
    expected = {(a, ch) for a in c["areas"] for ch in c["channels"]}
    keys = []
    if not isinstance(reference["rates"], list):
        raise ValueError("reference rate inventory required")
    for r in reference["rates"]:
        if not isinstance(r, dict) or set(r) != {
            "area_id",
            "channel",
            "rate",
            "dispersion",
            "mean_exposure",
            "baseline_days",
        }:
            raise ValueError("reference rate schema mismatch")
        keys.append((r["area_id"], r["channel"]))
        for field in ("rate", "dispersion", "mean_exposure"):
            v = r[field]
            if (
                type(v) not in (int, float)
                or not math.isfinite(v)
                or v <= 0
                or (field == "dispersion" and v < 1)
            ):
                raise ValueError("finite positive reference quantities required")
        if (
            type(r["baseline_days"]) is not int
            or r["baseline_days"] < c["min_baseline_days"]
        ):
            raise ValueError("insufficient reference baseline days")
    if len(keys) != len(set(keys)) or set(keys) != expected:
        raise ValueError("reference inventory mismatch")
    if set(reference["raw_count_baseline"]) != set(c["areas"]):
        raise ValueError("raw baseline inventory mismatch")
    for r in reference["raw_count_baseline"].values():
        if (
            set(r) != {"mean", "sd"}
            or any(
                type(v) not in (int, float) or not math.isfinite(v) or v <= 0
                for v in r.values()
            )
            or r["sd"] < 1
        ):
            raise ValueError("invalid raw baseline quantities")
    material = {k: v for k, v in reference.items() if k != "reference_id"}
    expected_id = (
        "signal-v1-"
        + hashlib.sha256(
            json.dumps(material, sort_keys=True, allow_nan=False).encode()
        ).hexdigest()[:16]
    )
    if reference["reference_id"] != expected_id:
        raise ValueError("reference integrity fingerprint mismatch")


@dataclass
class Cusum:
    up: float = 0.0
    down: float = 0.0
    up_streak: int = 0
    down_streak: int = 0
    recovery_streak: int = 0
    latched: str | None = None

    def reset(self):
        self.up = self.down = 0.0
        self.up_streak = self.down_streak = self.recovery_streak = 0
        self.latched = None

    def update(self, z: float, c: dict) -> str | None:
        if (
            isinstance(z, bool)
            or not isinstance(z, (int, float))
            or not math.isfinite(z)
        ):
            raise ValueError("finite numeric residual required")
        clipped = max(-c["cusum_clip"], min(c["cusum_clip"], z))
        k = c["cusum_k"]
        self.up = max(0.0, self.up + clipped - k)
        self.down = max(0.0, self.down - clipped - k)
        self.up_streak = self.up_streak + 1 if z > k else 0
        self.down_streak = self.down_streak + 1 if z < -k else 0
        self.recovery_streak = self.recovery_streak + 1 if abs(z) <= k else 0
        if self.latched and self.recovery_streak >= c["recovery_days"]:
            self.reset()
        direction = None
        if self.latched is None:
            if self.up >= c["cusum_h"] and self.up_streak >= c["min_shift_streak"]:
                direction = "UP"
            elif (
                self.down >= c["cusum_h"] and self.down_streak >= c["min_shift_streak"]
            ):
                direction = "DOWN"
            if direction:
                self.latched = direction
        return direction


def monitor(quality: list[dict], reference: dict, c: dict) -> list[dict]:
    if reference.get("policy") != c:
        raise ValueError("frozen reference/policy mismatch")
    for q in quality:
        if q["event_day"] > c["baseline_end"] and utc(q["monitor_at"]) <= utc(
            reference["released_at"]
        ):
            raise ValueError("historical reference unavailable at monitor origin")
    validate_reference(reference, c)
    rates = {(r["area_id"], r["channel"]): r for r in reference["rates"]}
    states = {area: Cusum() for area in c["areas"]}
    scored = []
    for q in sorted(quality, key=lambda q: (q["area_id"], q["event_day"])):
        if q["event_day"] <= c["baseline_end"]:
            continue
        if utc(q["monitor_at"]) <= utc(reference["released_at"]):
            raise ValueError("historical reference unavailable at monitor origin")
        state = states[q["area_id"]]
        row = {
            **q,
            "reference_id": reference["reference_id"],
            "policy_id": c["policy_id"],
            "expected_count": None,
            "expected_variance": None,
            "rate_per_1000": None,
            "standardized_residual": None,
            "exposure_ratio": None,
            "point_alert": False,
            "change_alert": False,
            "change_direction": None,
            "state_reset": not q["admitted"],
        }
        if not q["admitted"]:
            state.reset()
        else:
            expected = variance = training_exposure = 0.0
            for channel in c["channels"]:
                r = rates[q["area_id"], channel]
                exposure = q[channel + "_opportunities"]
                expected += r["rate"] * exposure
                variance += r["dispersion"] * r["rate"] * exposure
                training_exposure += r["mean_exposure"]
            z = (q["complaints"] - expected) / math.sqrt(max(variance, 1.0))
            direction = state.update(z, c)
            row.update(
                {
                    "expected_count": expected,
                    "expected_variance": variance,
                    "rate_per_1000": q["complaints"] / q["opportunities"] * 1000,
                    "standardized_residual": z,
                    "exposure_ratio": q["opportunities"] / training_exposure,
                    "point_alert": abs(z) >= c["point_limit"],
                    "change_alert": direction is not None,
                    "change_direction": direction,
                }
            )
        row["cusum_up"], row["cusum_down"] = state.up, state.down
        scored.append(row)
    return scored


def build_review_queue(scored: list[dict]) -> list[dict]:
    queue = []
    for row in scored:
        kinds = []
        if not row["admitted"]:
            kinds.append(("SIGNAL_QUALITY", 3, "CHECK_FEED", row["reason_codes"]))
        if row["change_alert"]:
            kinds.append(
                (
                    "RATE_SHIFT_ALERT",
                    2,
                    "REVIEW_SIGNAL_AND_CONTEXT",
                    '["CUSUM_SHIFT_ALERT"]',
                )
            )
        if row["point_alert"]:
            kinds.append(
                (
                    "POINT_ANOMALY",
                    1,
                    "REVIEW_SIGNAL_AND_CONTEXT",
                    '["POINT_LIMIT_EXCEEDED"]',
                )
            )
        for kind, priority, action, reasons in kinds:
            queue.append(
                {
                    "alert_id": f"{row['area_id']}:{row['event_day']}:{kind}",
                    "area_id": row["area_id"],
                    "event_day": row["event_day"],
                    "alert_type": kind,
                    "priority": priority,
                    "standardized_residual": row["standardized_residual"],
                    "reference_id": row["reference_id"],
                    "policy_id": row["policy_id"],
                    "reason_codes": reasons,
                    "review_status": "PENDING_REVIEW",
                    "recommended_action": action,
                    "adverse_action_authorized": False,
                }
            )
    queue.sort(
        key=lambda q: (
            -q["priority"],
            -abs(q["standardized_residual"] or 0.0),
            q["event_day"],
            q["area_id"],
            q["alert_type"],
        )
    )
    return [{"queue_rank": i + 1, **row} for i, row in enumerate(queue)]
