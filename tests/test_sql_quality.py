import json
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("duckdb")
import duckdb

ROOT = Path(__file__).resolve().parents[1]


def test_duckdb_quality(tmp_path):
    db = tmp_path / "demo.duckdb"
    out = tmp_path / "quality.json"
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "sql/bootstrap_duckdb.py"),
            "--input",
            str(ROOT / "data/synthetic/demo_panel.csv"),
            "--database",
            str(db),
            "--quality-output",
            str(out),
        ],
        check=True,
    )
    r = json.loads(out.read_text(encoding="utf-8"))
    assert r["status"] == "PASS"
    assert r["total_failures"] == 0


@pytest.mark.parametrize(
    "entity,outcome",
    [("E001", float("nan")), ("E001", float("inf")), (" E001", 1.0), ("", 1.0)],
)
def test_sql_rejects_nonfinite_outcomes_and_bad_identifiers(entity, outcome):
    with duckdb.connect() as con:
        con.execute(
            "CREATE SCHEMA core; CREATE SCHEMA mart; CREATE TABLE core.panel_observation(entity_id VARCHAR,period_id VARCHAR,feature_a DOUBLE,feature_b DOUBLE,outcome_value DOUBLE)"
        )
        con.execute(
            "INSERT INTO core.panel_observation VALUES (?, ?, ?, ?, ?)",
            [entity, "T01", 0.5, 0.5, outcome],
        )
        con.execute((ROOT / "sql/quality_checks.sql").read_text())
        assert (
            con.execute(
                "SELECT failure_count FROM mart.quality_results WHERE check_name='missing_required_values'"
            ).fetchone()[0]
            == 1
        )
