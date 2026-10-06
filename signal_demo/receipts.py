from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import tempfile
from pathlib import Path

import duckdb

from .contracts import FIELDS, calendar, strict_json, validate_records


def csv_text(rows, fields=None):
    out = io.StringIO(newline="")
    writer = csv.DictWriter(
        out, fieldnames=fields or list(rows[0]), lineterminator="\r\n"
    )
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue()


def _rows(path, fields):
    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        if (
            not reader.fieldnames
            or len(reader.fieldnames) != len(set(reader.fieldnames))
            or set(reader.fieldnames) != set(fields)
        ):
            raise ValueError("exact unique CSV schema required")
        rows = list(reader)
    for row in rows:
        if set(row) != set(fields) or any(
            not isinstance(v, str) or not v or v != v.strip() for v in row.values()
        ):
            raise ValueError("ragged, blank or padded raw CSV row")
    return rows


def _boolean(value):
    if value not in ("True", "False"):
        raise ValueError("canonical CSV boolean required")
    return value == "True"


def load_raw(path, c):
    rows = _rows(path, FIELDS)
    for row in rows:
        for field in ("complaints", "opportunities"):
            if not re.fullmatch(r"0|[1-9]\d*", row[field]):
                raise ValueError("canonical unsigned CSV integer required")
            row[field] = int(row[field])
        for field in ("complete", "synthetic_record"):
            row[field] = _boolean(row[field])
    validate_records(rows, c)
    return rows


def load_truth(path, c):
    rows = _rows(path, ("area_id", "event_day", "injected_event", "rate_anomaly"))
    expected = {(area, day) for area in c["areas"] for day in calendar(c)}
    seen = set()
    events = {
        "NONE",
        "POINT_SPIKE",
        "RATE_SHIFT",
        "ACCESS_CHANGE",
        "MISSING_CHANNEL",
        "LATE_DATA",
        "ZERO_EXPOSURE",
        "ZERO_REPORTS",
        "DUPLICATE_CHANNEL",
        "INCOMPLETE_BATCH",
    }
    for row in rows:
        key = (row["area_id"], row["event_day"])
        if key not in expected or key in seen or row["injected_event"] not in events:
            raise ValueError("invalid truth inventory")
        seen.add(key)
        row["rate_anomaly"] = _boolean(row["rate_anomaly"])
    if seen != expected:
        raise ValueError("incomplete truth inventory")
    return rows


def database_fingerprint(path):
    con = duckdb.connect(str(path), read_only=True)
    try:
        con.execute("SET TimeZone='UTC'")
        result = {}
        encode = lambda obj: json.dumps(obj, sort_keys=True, allow_nan=False)
        for schema, name in con.execute(
            "SELECT table_schema,table_name FROM information_schema.tables ORDER BY table_schema,table_name"
        ).fetchall():
            quoted = (
                '"' + schema.replace('"', '""') + '"."' + name.replace('"', '""') + '"'
            )
            result[schema + "." + name] = {
                "schema": con.execute(f"DESCRIBE {quoted}").fetchall(),
                "rows": sorted(
                    [
                        strict_json(row[0])
                        for row in con.execute(
                            f"SELECT to_json(r) FROM {quoted} AS r"
                        ).fetchall()
                    ],
                    key=encode,
                ),
            }
        return hashlib.sha256(encode(result).encode()).hexdigest()
    finally:
        con.close()


def verify_semantics(output, receipt):
    from . import pipeline
    from .detection import build_review_queue, fit_reference, monitor
    from .evaluation import evaluate
    from .quality import inspect
    from .warehouse import build

    c = pipeline.load_contract()
    rows = load_raw(output / "synthetic_signal_records.csv", c)
    truth = load_truth(output / "synthetic_injection_truth.csv", c)
    quality = inspect(rows, c)
    reference = fit_reference(rows, quality, c)
    scored = monitor(quality, reference, c)
    queue = build_review_queue(scored)
    load = lambda name: strict_json((output / name).read_text())
    same = lambda a, b: json.dumps(a, sort_keys=True, allow_nan=False) == json.dumps(
        b, sort_keys=True, allow_nan=False
    )
    if (
        not same(load("reference.json"), reference)
        or receipt["reference_id"] != reference["reference_id"]
    ):
        raise ValueError("reference semantic replay mismatch")
    if not same(load("manifest.json"), pipeline.make_manifest(c, reference)):
        raise ValueError(
            "source, dependency or policy manifest mismatch; regenerate outputs"
        )
    for name, values, fields in (
        ("quality_buckets.csv", quality, None),
        ("signal_monitor.csv", scored, None),
        ("review_queue.csv", queue, pipeline.QUEUE_FIELDS),
    ):
        if (output / name).read_bytes() != csv_text(values, fields).encode():
            raise ValueError(f"signal semantic table mismatch: {name}")
    if not same(load("evaluation.json"), evaluate(scored, truth, reference, c)):
        raise ValueError("evaluation semantic replay mismatch")
    with tempfile.TemporaryDirectory(prefix="signal-recheck-") as tmp:
        rebuilt = Path(tmp) / "signal.duckdb"
        qa = build(rebuilt, rows, quality, reference, scored, queue)
        if not same(
            load("signal_quality.json"), pipeline.quality_report(qa, quality, rows)
        ):
            raise ValueError("quality report semantic replay mismatch")
        if database_fingerprint(rebuilt) != database_fingerprint(
            output / "signal_monitor.duckdb"
        ):
            raise ValueError("independent database replay mismatch")
