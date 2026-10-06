from __future__ import annotations

from pathlib import Path

import duckdb

from .contracts import ROOT, calendar, monitor_at, utc, validate_records
from .detection import fit_reference, validate_reference
from .quality import inspect


def build(
    path: Path,
    rows: list[dict],
    quality: list[dict],
    reference: dict,
    scored: list[dict],
    queue: list[dict],
) -> dict:
    c = reference["policy"]
    validate_records(rows, c)
    validate_reference(reference, c)
    if quality != inspect(rows, c):
        raise ValueError(
            "signal warehouse QA failed: raw quality reconstruction mismatch"
        )
    reconstructed = fit_reference(rows, quality, c)
    for key in ("released_at", "baseline_input_sha256", "raw_count_baseline"):
        if reference[key] != reconstructed[key]:
            raise ValueError(
                f"signal warehouse QA failed: baseline lineage mismatch: {key}"
            )
    con = duckdb.connect(str(path))
    try:
        con.execute("SET TimeZone='UTC'")
        schema, reconstruction = (
            (ROOT / "sql/signals.sql").read_text().split("-- RECONSTRUCT AFTER LOADING")
        )
        con.execute(schema)

        def insert(name, values):
            if values:
                con.executemany(
                    f"INSERT INTO {name} VALUES ({','.join('?' for _ in values[0])})",
                    values,
                )

        insert(
            "signal_events",
            [
                [
                    r["record_id"],
                    r["area_id"],
                    r["event_day"],
                    r["channel"],
                    r["complaints"],
                    r["opportunities"],
                    utc(r["available_at"]),
                    r["complete"],
                    r["synthetic_record"],
                ]
                for r in rows
            ],
        )
        insert(
            "signal_schedule",
            [
                [area, day, monitor_at(day, c)]
                for area in c["areas"]
                for day in calendar(c)
            ],
        )
        insert(
            "signal_policy",
            [
                [
                    c["baseline_end"],
                    c["point_limit"],
                    c["max_latency_hours"],
                    c["cusum_k"],
                    c["cusum_h"],
                    c["cusum_clip"],
                    c["min_shift_streak"],
                    c["recovery_days"],
                    c["min_baseline_days"],
                    c["min_baseline_events"],
                    reference["reference_id"],
                    c["policy_id"],
                ]
            ],
        )
        insert(
            "signal_quality",
            [
                [
                    q["area_id"],
                    q["event_day"],
                    utc(q["monitor_at"]),
                    q["admitted"],
                    q["reason_codes"],
                    q["complaints"],
                    q["opportunities"],
                ]
                for q in quality
            ],
        )
        insert(
            "signal_reference",
            [
                [
                    r["area_id"],
                    r["channel"],
                    r["rate"],
                    r["dispersion"],
                    r["mean_exposure"],
                    r["baseline_days"],
                ]
                for r in reference["rates"]
            ],
        )
        fields = (
            "area_id",
            "event_day",
            "admitted",
            "expected_count",
            "expected_variance",
            "standardized_residual",
            "point_alert",
            "change_alert",
            "reference_id",
            "change_direction",
            "cusum_up",
            "cusum_down",
            "rate_per_1000",
            "exposure_ratio",
            "state_reset",
            "policy_id",
        )
        insert("signal_monitor", [[m[k] for k in fields] for m in scored])
        fields = (
            "queue_rank",
            "alert_id",
            "area_id",
            "event_day",
            "alert_type",
            "priority",
            "standardized_residual",
            "reference_id",
            "policy_id",
            "reason_codes",
            "review_status",
            "recommended_action",
            "adverse_action_authorized",
        )
        insert("signal_review", [[q[k] for k in fields] for q in queue])
        con.execute(reconstruction)
        queries = {
            "duplicate_quality_buckets": "SELECT COUNT(*) FROM (SELECT area_id,event_day FROM signal_quality GROUP BY ALL HAVING COUNT(*)>1)",
            "quality_inventory": "SELECT COUNT(*) FROM signal_schedule s FULL JOIN signal_quality q USING(area_id,event_day) WHERE s.area_id IS NULL OR q.area_id IS NULL OR s.monitor_at IS DISTINCT FROM q.monitor_at",
            "raw_quality_admission_and_reasons": "SELECT COUNT(*) FROM mart.signal_raw_quality s JOIN signal_quality q USING(area_id,event_day) WHERE (s.admitted,s.reason_codes) IS DISTINCT FROM (q.admitted,q.reason_codes)",
            "python_sql_count_exposure_parity": "SELECT COUNT(*) FROM mart.signal_raw_quality s JOIN signal_quality q USING(area_id,event_day) WHERE q.complaints IS DISTINCT FROM CASE WHEN s.admitted THEN s.complaints END OR q.opportunities IS DISTINCT FROM CASE WHEN s.admitted THEN s.opportunities END",
            "synthetic_raw_flags": "SELECT COUNT(*) FROM signal_events WHERE synthetic_record IS DISTINCT FROM true",
            "future_or_incomplete_admitted": "SELECT COUNT(*) FROM signal_events e JOIN signal_quality q USING(area_id,event_day) WHERE q.admitted AND (e.available_at>q.monitor_at OR NOT e.complete OR e.opportunities=0)",
            "blocked_buckets_scored": "SELECT COUNT(*) FROM signal_monitor WHERE NOT admitted AND (standardized_residual IS NOT NULL OR expected_count IS NOT NULL OR expected_variance IS NOT NULL OR point_alert IS DISTINCT FROM false OR change_alert IS DISTINCT FROM false)",
            "admitted_buckets_unscored": "SELECT COUNT(*) FROM signal_monitor WHERE admitted AND (expected_count IS NULL OR expected_variance IS NULL OR standardized_residual IS NULL OR NOT ISFINITE(expected_count) OR NOT ISFINITE(expected_variance) OR NOT ISFINITE(standardized_residual))",
            "duplicate_monitor_buckets": "SELECT COUNT(*) FROM (SELECT area_id,event_day FROM signal_monitor GROUP BY ALL HAVING COUNT(*)>1)",
            "monitor_inventory_mismatch": "SELECT COUNT(*) FROM mart.signal_sql_scored s FULL JOIN signal_monitor m USING(area_id,event_day) WHERE s.area_id IS NULL OR m.area_id IS NULL OR m.admitted IS DISTINCT FROM s.admitted",
            "reference_inventory": "SELECT COUNT(*) FROM mart.signal_baseline b FULL JOIN signal_reference r USING(area_id,channel) WHERE b.area_id IS NULL OR r.area_id IS NULL",
            "duplicate_reference_keys": "SELECT COUNT(*) FROM (SELECT area_id,channel FROM signal_reference GROUP BY ALL HAVING COUNT(*)>1)",
            "finite_positive_reference": "SELECT COUNT(*) FROM signal_reference WHERE rate IS NULL OR dispersion IS NULL OR mean_exposure IS NULL OR NOT ISFINITE(rate) OR NOT ISFINITE(dispersion) OR NOT ISFINITE(mean_exposure) OR rate<=0 OR dispersion<1 OR mean_exposure<=0",
            "minimum_baseline_coverage": "SELECT COUNT(*) FROM mart.signal_baseline b CROSS JOIN signal_policy p WHERE b.baseline_days<p.min_baseline_days OR b.events<p.min_baseline_events",
            "python_sql_baseline_rate_parity": "SELECT COUNT(*) FROM mart.signal_baseline b JOIN signal_reference r USING(area_id,channel) WHERE r.rate IS NULL OR ABS(b.rate-r.rate)>1e-12",
            "independent_baseline_dispersion_exposure": "SELECT COUNT(*) FROM mart.signal_baseline b JOIN signal_reference r USING(area_id,channel) WHERE r.dispersion IS NULL OR r.mean_exposure IS NULL OR ABS(b.dispersion-r.dispersion)>1e-10 OR ABS(b.mean_exposure-r.mean_exposure)>1e-10 OR b.baseline_days IS DISTINCT FROM r.baseline_days",
            "python_sql_expected_residual_parity": "SELECT COUNT(*) FROM mart.signal_sql_scored s JOIN signal_monitor m USING(area_id,event_day) WHERE s.admitted AND (m.expected_count IS NULL OR m.expected_variance IS NULL OR m.standardized_residual IS NULL OR ABS(s.expected_count-m.expected_count)>1e-10 OR ABS(s.expected_variance-m.expected_variance)>1e-10 OR ABS(s.z-m.standardized_residual)>1e-10)",
            "rate_and_exposure_ratio_parity": "SELECT COUNT(*) FROM mart.signal_sql_scored s JOIN signal_monitor m USING(area_id,event_day) WHERE (s.admitted AND (m.rate_per_1000 IS NULL OR m.exposure_ratio IS NULL OR NOT ISFINITE(m.rate_per_1000) OR NOT ISFINITE(m.exposure_ratio) OR ABS(s.rate_per_1000-m.rate_per_1000)>1e-10 OR ABS(s.exposure_ratio-m.exposure_ratio)>1e-10)) OR (NOT s.admitted AND (m.rate_per_1000 IS NOT NULL OR m.exposure_ratio IS NOT NULL))",
            "point_alert_parity": "SELECT COUNT(*) FROM mart.signal_sql_scored s JOIN signal_monitor m USING(area_id,event_day) CROSS JOIN signal_policy p WHERE m.point_alert IS DISTINCT FROM CASE WHEN s.admitted THEN abs(s.z)>=p.point_limit ELSE false END",
            "independent_cusum_state": "SELECT COUNT(*) FROM mart.signal_sql_cusum s JOIN signal_monitor m USING(area_id,event_day) WHERE m.cusum_up IS NULL OR m.cusum_down IS NULL OR NOT ISFINITE(m.cusum_up) OR NOT ISFINITE(m.cusum_down) OR ABS(s.up-m.cusum_up)>1e-10 OR ABS(s.down-m.cusum_down)>1e-10 OR m.change_direction IS DISTINCT FROM s.direction OR m.change_alert IS DISTINCT FROM (s.direction IS NOT NULL)",
            "monitor_policy_and_reset": "SELECT COUNT(*) FROM signal_monitor m CROSS JOIN signal_policy p WHERE m.reference_id IS DISTINCT FROM p.reference_id OR m.policy_id IS DISTINCT FROM p.policy_id OR m.state_reset IS DISTINCT FROM (NOT m.admitted)",
            "review_queue_coverage": "SELECT COUNT(*) FROM mart.signal_expected_review e FULL JOIN signal_review q USING(alert_id) WHERE e.alert_id IS NULL OR q.alert_id IS NULL",
            "review_queue_metadata": "SELECT COUNT(*) FROM mart.signal_expected_review e JOIN signal_review q USING(alert_id) WHERE (e.queue_rank,e.area_id,e.event_day,e.alert_type,e.priority,e.reference_id,e.policy_id,e.reason_codes,e.recommended_action,'PENDING_REVIEW') IS DISTINCT FROM (q.queue_rank,q.area_id,q.event_day,q.alert_type,q.priority,q.reference_id,q.policy_id,q.reason_codes,q.recommended_action,q.review_status)",
            "review_queue_residual": "SELECT COUNT(*) FROM mart.signal_expected_review e JOIN signal_review q USING(alert_id) WHERE (e.z IS NULL)<>(q.standardized_residual IS NULL) OR (e.z IS NOT NULL AND (NOT ISFINITE(q.standardized_residual) OR ABS(e.z-q.standardized_residual)>1e-10))",
            "unauthorized_adverse_action": "SELECT COUNT(*) FROM signal_review WHERE adverse_action_authorized IS DISTINCT FROM false",
            "duplicate_alert_id": "SELECT COUNT(*) FROM (SELECT alert_id FROM signal_review GROUP BY alert_id HAVING COUNT(*)>1)",
        }
        checks = {
            name: int(con.execute(query).fetchone()[0])
            for name, query in queries.items()
        }
        result = {
            "status": "PASS" if not any(checks.values()) else "FAIL",
            "total_failures": sum(checks.values()),
            "checks": checks,
            "blocked_monitor_buckets": sum(not m["admitted"] for m in scored),
            "blocked_is_expected_handling": True,
        }
    finally:
        con.close()
    if result["status"] != "PASS":
        raise ValueError(
            f"signal warehouse QA failed: { {k: v for k, v in checks.items() if v} }"
        )
    return result
