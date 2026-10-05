#!/usr/bin/env python3
"""Small synthetic fixed-effects demonstration; not the private study specification."""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np


def main(path: str) -> int:
    rows=[]
    with Path(path).open(newline='', encoding='utf-8') as f:
        for r in csv.DictReader(f):
            rows.append((r['entity_id'], float(r['feature_a']), float(r['feature_b']), float(r['outcome_value'])))

    means=defaultdict(lambda: np.zeros(3))
    counts=defaultdict(int)
    for entity,a,b,y in rows:
        means[entity] += np.array([a,b,y])
        counts[entity] += 1
    for k in means:
        means[k] /= counts[k]

    X=[]; Y=[]
    for entity,a,b,y in rows:
        ma,mb,my=means[entity]
        X.append([a-ma,b-mb])
        Y.append(y-my)
    beta=np.linalg.lstsq(np.asarray(X), np.asarray(Y), rcond=None)[0]
    print(f'SYNTHETIC_WITHIN_BETA_FEATURE_A={beta[0]:.6f}')
    print(f'SYNTHETIC_WITHIN_BETA_FEATURE_B={beta[1]:.6f}')
    print('SCIENTIFIC_RESULT_CLAIMED=false')
    return 0

if __name__=='__main__':
    raise SystemExit(main(sys.argv[1]))
