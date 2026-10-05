#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument('--monitor', required=True)
    ap.add_argument('--quality', required=True)
    ap.add_argument('--json-output', required=True)
    ap.add_argument('--markdown-output', required=True)
    args=ap.parse_args()

    monitor=json.loads(Path(args.monitor).read_text(encoding='utf-8'))
    quality=json.loads(Path(args.quality).read_text(encoding='utf-8'))
    overall='PASS' if monitor.get('status')=='PASS' and quality.get('status')=='PASS' else 'FAIL'

    result={
        'status':overall,
        'scope':'public_synthetic_engineering_demo',
        'monitor':monitor,
        'sql_quality':quality,
        'scientific_result_claimed':False,
        'private_research_reproduced':False,
    }

    Path(args.json_output).write_text(json.dumps(result, indent=2, sort_keys=True)+'\n', encoding='utf-8')
    md=f"""# Public Engineering Demo Report\n\n**Status:** {overall}\n\n- Synthetic rows: {monitor.get('rows')}\n- Synthetic entities: {monitor.get('unique_entities')}\n- Synthetic periods: {monitor.get('unique_periods')}\n- SQL quality failures: {quality.get('total_failures')}\n- Scientific result claimed: **No**\n- Private research reproduced: **No**\n\nThis report validates only the public synthetic engineering companion.\n"""
    Path(args.markdown_output).write_text(md, encoding='utf-8')
    print(f'REPORT_STATUS={overall}')
    return 0 if overall=='PASS' else 1

if __name__ == '__main__':
    raise SystemExit(main())
