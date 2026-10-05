from __future__ import annotations

from pathlib import Path
import duckdb

from .contracts import ROOT, utc


def build(path: Path, rows: list[dict], quality: list[dict], reference: dict, scored: list[dict], queue: list[dict]) -> dict:
    con = duckdb.connect(str(path))
    try:
        con.execute("SET TimeZone='UTC'")
        con.execute((ROOT / "sql/signals.sql").read_text())
        con.executemany("INSERT INTO signal_events VALUES (?,?,?,?,?,?,?,?,?)", [
            [r["record_id"], r["area_id"], r["event_day"], r["channel"],
             r["complaints"], r["opportunities"], utc(r["available_at"]),
             r["complete"], r["synthetic_record"]] for r in rows
        ])
        con.executemany("INSERT INTO signal_quality VALUES (?,?,?,?,?,?,?)", [
            [q["area_id"], q["event_day"], utc(q["monitor_at"]), q["admitted"],
             q["reason_codes"], q["complaints"], q["opportunities"]] for q in quality
        ])
        con.executemany("INSERT INTO signal_reference VALUES (?,?,?,?,?)", [
            [r["area_id"], r["channel"], r["rate"], r["dispersion"], r["mean_exposure"]]
            for r in reference["rates"]
        ])
        con.executemany("INSERT INTO signal_monitor VALUES (?,?,?,?,?,?,?,?,?)", [
            [m["area_id"], m["event_day"], m["admitted"], m["expected_count"],
             m["expected_variance"], m["standardized_residual"], m["point_alert"],
             m["change_alert"], m["reference_id"]] for m in scored
        ])
        if queue:
            con.executemany("INSERT INTO signal_review VALUES (?,?,?,?,?,?,?)", [
                [q["alert_id"], q["area_id"], q["event_day"], q["alert_type"],
                 q["priority"], q["review_status"], q["adverse_action_authorized"]] for q in queue
            ])
        queries = {
            "duplicate_quality_buckets": "SELECT COUNT(*) FROM (SELECT area_id,event_day FROM signal_quality GROUP BY ALL HAVING COUNT(*)>1)",
            "future_or_incomplete_admitted": """SELECT COUNT(*) FROM signal_events e
                JOIN signal_quality q USING (area_id,event_day)
                WHERE q.admitted AND (e.available_at>q.monitor_at OR NOT e.complete OR e.opportunities=0)""",
            "blocked_buckets_scored": """SELECT COUNT(*) FROM signal_monitor WHERE NOT admitted
                AND (standardized_residual IS NOT NULL OR expected_count IS NOT NULL
                    OR expected_variance IS NOT NULL OR point_alert OR change_alert)""",
            "admitted_buckets_unscored": """SELECT COUNT(*) FROM signal_monitor WHERE admitted
                AND (expected_count IS NULL OR expected_variance IS NULL OR standardized_residual IS NULL
                    OR NOT ISFINITE(expected_count) OR NOT ISFINITE(expected_variance)
                    OR NOT ISFINITE(standardized_residual))""",
            "monitor_inventory_mismatch": """SELECT COUNT(*) FROM signal_quality q
                FULL OUTER JOIN signal_monitor m USING (area_id,event_day)
                WHERE (q.event_day>CAST(? AS DATE) AND
                    (m.event_day IS NULL OR m.admitted IS DISTINCT FROM q.admitted))
                    OR (m.event_day IS NOT NULL AND (q.event_day IS NULL OR q.event_day<=CAST(? AS DATE)))""",
            "python_sql_count_exposure_parity": """SELECT COUNT(*) FROM signal_quality q
                JOIN mart.signal_expectation e USING (area_id,event_day)
                WHERE q.admitted AND (q.complaints<>e.complaints OR q.opportunities<>e.opportunities)""",
            "python_sql_expected_residual_parity": """SELECT COUNT(*) FROM signal_monitor m
                JOIN mart.signal_expectation e USING (area_id,event_day)
                WHERE m.admitted AND (ABS(m.expected_count-e.expected_count)>1e-10
                    OR ABS(m.expected_variance-e.expected_variance)>1e-10
                    OR ABS(m.standardized_residual-(e.complaints-e.expected_count)/SQRT(GREATEST(e.expected_variance,1.0)))>1e-10)""",
            "python_sql_baseline_rate_parity": """SELECT COUNT(*) FROM (
                SELECT e.area_id,e.channel,SUM(e.complaints)::DOUBLE/SUM(e.opportunities) AS rate
                FROM signal_events e JOIN signal_quality q USING (area_id,event_day)
                WHERE q.admitted AND e.event_day<=CAST(? AS DATE) GROUP BY e.area_id,e.channel
                ) b JOIN signal_reference r USING (area_id,channel) WHERE ABS(b.rate-r.rate)>1e-12""",
            "unauthorized_adverse_action": "SELECT COUNT(*) FROM signal_review WHERE adverse_action_authorized",
            "duplicate_alert_id": "SELECT COUNT(*) FROM (SELECT alert_id FROM signal_review GROUP BY alert_id HAVING COUNT(*)>1)",
        }
        checks = {}
        for name, query in queries.items():
            params = [reference["baseline_end"]] if name == "python_sql_baseline_rate_parity" else []
            if name == "monitor_inventory_mismatch":
                params = [reference["baseline_end"]]*2
            checks[name] = int(con.execute(query, params).fetchone()[0])
        result = {
            "status": "PASS" if not any(checks.values()) else "FAIL",
            "total_failures": sum(checks.values()), "checks": checks,
            "blocked_monitor_buckets": sum(not m["admitted"] for m in scored),
            "blocked_is_expected_handling": True,
        }
    finally:
        con.close()
    if result["status"] != "PASS":
        raise ValueError("signal warehouse QA failed")
    return result
