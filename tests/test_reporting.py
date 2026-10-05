import json, subprocess, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def test_report_builder(tmp_path):
    mon=tmp_path/'m.json'; qual=tmp_path/'q.json'; jout=tmp_path/'r.json'; mout=tmp_path/'r.md'
    mon.write_text(json.dumps({'status':'PASS','rows':480,'unique_entities':40,'unique_periods':12}), encoding='utf-8')
    qual.write_text(json.dumps({'status':'PASS','total_failures':0}), encoding='utf-8')
    subprocess.run([sys.executable, str(ROOT/'src/reporting/build_report.py'), '--monitor',str(mon),'--quality',str(qual),'--json-output',str(jout),'--markdown-output',str(mout)], check=True)
    r=json.loads(jout.read_text(encoding='utf-8'))
    assert r['status']=='PASS'
    assert r['scientific_result_claimed'] is False
    assert r['private_research_reproduced'] is False
