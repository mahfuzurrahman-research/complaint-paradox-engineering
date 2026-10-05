#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

REQUIRED = ('entity_id','period_id','feature_a','feature_b','outcome_value')
EXPECTED_ROWS = 480
EXPECTED_ENTITIES = 40
EXPECTED_PERIODS = 12


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def inspect(path: Path) -> dict:
    errors=[]
    rows=0
    entities=set()
    periods=set()
    keys=set()
    duplicates=0
    missing=0
    range_failures=0

    with path.open(newline='', encoding='utf-8') as f:
        reader=csv.DictReader(f)
        columns=tuple(reader.fieldnames or [])
        missing_cols=[c for c in REQUIRED if c not in columns]
        if missing_cols:
            return {'status':'FAIL','errors':[f'MISSING_COLUMNS:{",".join(missing_cols)}']}

        for row in reader:
            rows += 1
            entity=(row['entity_id'] or '').strip()
            period=(row['period_id'] or '').strip()
            key=(entity,period)
            if key in keys:
                duplicates += 1
            keys.add(key)
            entities.add(entity)
            periods.add(period)

            vals=[]
            for c in ('feature_a','feature_b','outcome_value'):
                raw=(row[c] or '').strip()
                if raw == '':
                    missing += 1
                    vals.append(float('nan'))
                else:
                    vals.append(float(raw))
            a,b,y=vals
            if any(not math.isfinite(v) for v in vals):
                missing += 1
            if math.isfinite(a) and not (0 <= a <= 1):
                range_failures += 1
            if math.isfinite(b) and not (0 <= b <= 1):
                range_failures += 1

    checks={
        'rows': rows == EXPECTED_ROWS,
        'entities': len(entities) == EXPECTED_ENTITIES,
        'periods': len(periods) == EXPECTED_PERIODS,
        'duplicate_keys': duplicates == 0,
        'missing_numeric_values': missing == 0,
        'synthetic_ranges': range_failures == 0,
    }
    errors=[k for k,v in checks.items() if not v]
    return {
        'status':'PASS' if not errors else 'FAIL',
        'errors':errors,
        'rows':rows,
        'unique_entities':len(entities),
        'unique_periods':len(periods),
        'duplicate_keys':duplicates,
        'missing_numeric_values':missing,
        'range_failures':range_failures,
        'sha256':sha256(path),
        'checks':checks,
        'scope':'synthetic_public_demo_only',
    }


def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument('--input', required=True)
    ap.add_argument('--output', required=True)
    args=ap.parse_args()
    result=inspect(Path(args.input))
    out=Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True)+'\n', encoding='utf-8')
    print(f"MONITOR_STATUS={result['status']}")
    return 0 if result['status']=='PASS' else 1

if __name__ == '__main__':
    raise SystemExit(main())
