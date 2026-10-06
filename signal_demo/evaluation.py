from __future__ import annotations

from collections import Counter
from datetime import date


def evaluate(scored: list[dict], truth: list[dict], reference: dict, c: dict) -> dict:
    """Offline injection checks only: operational code never receives truth."""
    labels = {(t["area_id"], t["event_day"]): t for t in truth}
    eligible = [s for s in scored if s["admitted"]]
    confusion = Counter()
    for row in eligible:
        actual = labels[row["area_id"], row["event_day"]]["rate_anomaly"]
        predicted = row["point_alert"]
        confusion[
            ("true_" if actual == predicted else "false_")
            + ("positive" if predicted else "negative")
        ] += 1
    scenarios = {}
    for event in sorted(
        {labels[s["area_id"], s["event_day"]]["injected_event"] for s in scored}
    ):
        selected = [
            s
            for s in scored
            if labels[s["area_id"], s["event_day"]]["injected_event"] == event
        ]
        admitted = [s for s in selected if s["admitted"]]
        scenarios[event] = {
            "scheduled_buckets": len(selected),
            "admitted_buckets": len(admitted),
            "blocked_buckets": len(selected) - len(admitted),
            "point_alerts": sum(s["point_alert"] for s in admitted),
            "change_alerts": sum(s["change_alert"] for s in admitted),
        }
    changes = []
    for area in c["areas"]:
        onset = sorted(
            t["event_day"]
            for t in truth
            if t["area_id"] == area and t["injected_event"] == "RATE_SHIFT"
        )
        if not onset:
            continue
        detections = sorted(
            s["event_day"]
            for s in scored
            if s["area_id"] == area
            and s["event_day"] >= onset[0]
            and s["change_direction"] == "UP"
        )
        first = detections[0] if detections else None
        changes.append(
            {
                "area_id": area,
                "injected_onset": onset[0],
                "first_up_alert": first,
                "delay_days": (
                    date.fromisoformat(first) - date.fromisoformat(onset[0])
                ).days
                if first
                else None,
            }
        )
    access = [
        s
        for s in eligible
        if labels[s["area_id"], s["event_day"]]["injected_event"] == "ACCESS_CHANGE"
    ]
    naive_alerts = sum(
        abs(
            (s["complaints"] - reference["raw_count_baseline"][s["area_id"]]["mean"])
            / reference["raw_count_baseline"][s["area_id"]]["sd"]
        )
        >= c["point_limit"]
        for s in access
    )
    return {
        "evaluation_scope": "seeded fabricated injections; descriptive engineering checks, not real-world performance",
        "truth_used_by_detector": False,
        "policy_tuned_on_evaluation": False,
        "admitted_monitor_buckets": len(eligible),
        "blocked_monitor_buckets": len(scored) - len(eligible),
        "point_bucket_confusion": {
            k: confusion[k]
            for k in [
                "true_positive",
                "false_positive",
                "false_negative",
                "true_negative",
            ]
        },
        "scenarios": scenarios,
        "sustained_shift_detection": changes,
        "change_alerts_outside_injected_shift": sum(
            s["change_alert"]
            and labels[s["area_id"], s["event_day"]]["injected_event"] != "RATE_SHIFT"
            for s in eligible
        ),
        "access_change_comparison": {
            "admitted_buckets": len(access),
            "naive_count_point_alerts": naive_alerts,
            "exposure_normalized_point_alerts": sum(s["point_alert"] for s in access),
            "exposure_normalized_change_alerts": sum(s["change_alert"] for s in access),
        },
        "limitations": [
            "One fixed seed and deliberately simple synthetic mechanisms.",
            "The declared denominator is fabricated; its real-world validity is not established.",
            "Residual thresholds and modified CUSUM have no calibrated false-alarm guarantee.",
            "A complaint-rate alert does not establish underlying failure, negligence or citizen need.",
        ],
    }
