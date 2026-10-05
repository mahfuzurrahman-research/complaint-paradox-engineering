#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb

ROOT=Path(__file__).resolve().parent


def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument('--input', required=True)
    ap.add_argument('--database', required=True)
    ap.add_argument('--quality-output', required=True)
    args=ap.parse_args()

    db=Path(args.database)
    db.parent.mkdir(parents=True, exist_ok=True)
    con=duckdb.connect(str(db))
    try:
        con.execute("SET VARIABLE input_path = ?", [str(Path(args.input).resolve())])
        schema=(ROOT/'schema.sql').read_text(encoding='utf-8')
        # DuckDB parameters cannot be interpolated inside read_csv_auto through
        # $variable in all versions, so substitute only the escaped synthetic path.
        quoted=str(Path(args.input).resolve()).replace("'", "''")
        schema=schema.replace('$input_path', f"'{quoted}'")
        con.execute(schema)
        con.execute((ROOT/'marts.sql').read_text(encoding='utf-8'))
        con.execute((ROOT/'quality_checks.sql').read_text(encoding='utf-8'))
        rows=con.execute('SELECT check_name, failure_count FROM mart.quality_results ORDER BY check_name').fetchall()
        total=sum(int(r[1]) for r in rows)
        result={
            'status':'PASS' if total==0 else 'FAIL',
            'total_failures':total,
            'checks':[{'check_name':r[0],'failure_count':int(r[1])} for r in rows],
            'scope':'synthetic_public_demo_only',
        }
    finally:
        con.close()

    Path(args.quality_output).write_text(json.dumps(result, indent=2, sort_keys=True)+'\n', encoding='utf-8')
    print(f"SQL_QUALITY_STATUS={result['status']}")
    return 0 if result['status']=='PASS' else 1

if __name__ == '__main__':
    raise SystemExit(main())
