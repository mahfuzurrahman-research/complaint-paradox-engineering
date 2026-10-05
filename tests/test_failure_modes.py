from pathlib import Path
import csv, importlib.util

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('panel_monitor', ROOT/'src/monitoring/panel_monitor.py')
mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)

def test_duplicate_key_fails(tmp_path):
    src=ROOT/'data/synthetic/demo_panel.csv'
    dst=tmp_path/'dup.csv'
    rows=list(csv.reader(src.open(newline='', encoding='utf-8')))
    rows.append(rows[1])
    with dst.open('w', newline='', encoding='utf-8') as f:
        csv.writer(f).writerows(rows)
    r=mod.inspect(dst)
    assert r['status']=='FAIL'
    assert r['duplicate_keys']>0

def test_missing_column_fails(tmp_path):
    p=tmp_path/'bad.csv'
    p.write_text('entity_id,period_id\nE001,T01\n', encoding='utf-8')
    r=mod.inspect(p)
    assert r['status']=='FAIL'
    assert any(x.startswith('MISSING_COLUMNS:') for x in r['errors'])
