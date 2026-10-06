import csv
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "panel_monitor", ROOT / "src/monitoring/panel_monitor.py"
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def test_duplicate_key_fails(tmp_path):
    src = ROOT / "data/synthetic/demo_panel.csv"
    dst = tmp_path / "dup.csv"
    rows = list(csv.reader(src.open(newline="", encoding="utf-8")))
    rows.append(rows[1])
    with dst.open("w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)
    r = mod.inspect(dst)
    assert r["status"] == "FAIL"
    assert r["duplicate_keys"] > 0


def test_missing_column_fails(tmp_path):
    p = tmp_path / "bad.csv"
    p.write_text("entity_id,period_id\nE001,T01\n", encoding="utf-8")
    r = mod.inspect(p)
    assert r["status"] == "FAIL"
    assert any(x.startswith("MISSING_COLUMNS:") for x in r["errors"])


@pytest.mark.parametrize(
    "corruption", ["duplicate_header", "ragged", "padded_id", "nonnumeric", "nonfinite"]
)
def test_malformed_panel_returns_structured_failure(tmp_path, corruption):
    with (ROOT / "data/synthetic/demo_panel.csv").open(
        newline="", encoding="utf-8"
    ) as source:
        rows = list(csv.reader(source))
    if corruption == "duplicate_header":
        rows[0][1] = rows[0][0]
    elif corruption == "ragged":
        rows[1].append("unexpected")
    elif corruption == "padded_id":
        rows[1][0] = " " + rows[1][0]
    else:
        rows[1][-1] = "bad-number" if corruption == "nonnumeric" else "nan"
    path = tmp_path / "malformed.csv"
    with path.open("w", newline="", encoding="utf-8") as dest:
        csv.writer(dest).writerows(rows)
    result = mod.inspect(path)
    assert result["status"] == "FAIL" and result["errors"]
