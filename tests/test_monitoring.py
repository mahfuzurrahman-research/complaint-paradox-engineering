from pathlib import Path
import importlib.util

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('panel_monitor', ROOT/'src/monitoring/panel_monitor.py')
mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)

def test_synthetic_panel_passes():
    r=mod.inspect(ROOT/'data/synthetic/demo_panel.csv')
    assert r['status']=='PASS'
    assert r['rows']==480
    assert r['unique_entities']==40
    assert r['unique_periods']==12
