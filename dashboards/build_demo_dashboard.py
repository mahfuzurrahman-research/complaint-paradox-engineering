#!/usr/bin/env python3
from __future__ import annotations

import argparse, html, json
from pathlib import Path


def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument('--report', required=True)
    ap.add_argument('--output', required=True)
    args=ap.parse_args()
    r=json.loads(Path(args.report).read_text(encoding='utf-8'))
    m=r['monitor']; q=r['sql_quality']
    doc=f'''<!doctype html>
<html><head><meta charset="utf-8"><title>Public Engineering Demo</title>
<style>body{{font-family:system-ui;max-width:900px;margin:40px auto;padding:0 20px}}table{{border-collapse:collapse}}td,th{{border:1px solid #ccc;padding:8px}}code{{background:#f3f3f3;padding:2px 4px}}</style></head>
<body><h1>Complaint Paradox — Public Engineering Demo</h1>
<p><strong>Status:</strong> {html.escape(r['status'])}</p>
<table><tr><th>Metric</th><th>Value</th></tr>
<tr><td>Synthetic rows</td><td>{m['rows']}</td></tr>
<tr><td>Synthetic entities</td><td>{m['unique_entities']}</td></tr>
<tr><td>Synthetic periods</td><td>{m['unique_periods']}</td></tr>
<tr><td>SQL quality failures</td><td>{q['total_failures']}</td></tr></table>
<h2>Boundary</h2><p>This dashboard reports only a synthetic public engineering demonstration. It does not expose or reproduce the private scientific study.</p>
</body></html>'''
    Path(args.output).write_text(doc, encoding='utf-8')
    print('DASHBOARD_STATUS=PASS')
    return 0

if __name__=='__main__':
    raise SystemExit(main())
