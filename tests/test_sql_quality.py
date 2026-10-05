from pathlib import Path
import json, subprocess, sys
import pytest

pytest.importorskip('duckdb')
ROOT=Path(__file__).resolve().parents[1]

def test_duckdb_quality(tmp_path):
    db=tmp_path/'demo.duckdb'; out=tmp_path/'quality.json'
    subprocess.run([sys.executable, str(ROOT/'sql/bootstrap_duckdb.py'), '--input',str(ROOT/'data/synthetic/demo_panel.csv'),'--database',str(db),'--quality-output',str(out)], check=True)
    r=json.loads(out.read_text(encoding='utf-8'))
    assert r['status']=='PASS'
    assert r['total_failures']==0
