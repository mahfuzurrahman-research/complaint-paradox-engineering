# Observed local validation

Validated on 2026-10-05 UTC using Python 3.12.14 on Linux, NumPy 2.3.5,
DuckDB 1.5.6 and pytest 9.1.1. These are actual local observations from
`bash run_all_demos.sh`, not results from a hosted CI or Docker run.

## Execution and integrity

| Check | Observed result |
|---|---|
| Original synthetic panel, SQL, reports and dashboard | PASS |
| Original tests | 5 passed |
| Signal tests | 38 passed |
| Total local tests | 43 passed; no skipped tests |
| Signal pipeline and receipt verification | PASS |
| Independent DuckDB checks | 10 checks, zero failures |
| Saved-reference replay | Identical scores and queue |
| Repeated runs | Identical data CSV/JSON files and manifest |
| Future perturbation | Baseline and earlier scores unchanged |
| Corruption/incomplete receipt | Rejected |
| Missing/null/corrupted SQL scores | Rejected |
| Staging failure | Previous completed output preserved |
| Concurrent writer | Rejected; lock released after failure |
| Dependency compatibility | `python -m pip check` passed |

Docker was unavailable in the local environment. The workflow is configured to
execute the combined pipelines and Docker build/run on GitHub; a completed hosted
run is required before claiming either hosted CI or container execution passed
for this upgrade. The repository's earlier passing workflow belongs to the
previous revision and does not validate this new code.

## Fixed-seed injection observations

The default stream uses seed `20261006`, policy `synthetic-signal-v1` and reference
`signal-v1-e5d10fd3709c3b5b`. There are 2,014 raw records and 1,008 scheduled
area/day buckets: 336 baseline buckets and 672 later monitoring buckets. Nine
monitoring buckets are blocked, leaving 663 eligible buckets. One genuine zero
is admitted. The queue contains 60 review rows: nine quality reviews, one change
alert and 50 point alerts. A bucket may have both point and change review rows.

| Injected condition | Observed behavior |
|---|---|
| Single point spike | One point alert; no change alert |
| Sustained doubled rate | First UP change alert after 3 days; 48 of 84 days exceed the point threshold |
| Access growth, unchanged channel rates | 0 point/change alerts across 91 days; naive raw-count rule flags all 91 |
| Missing channel | All 3 affected buckets blocked |
| Late/unavailable batch | All 3 affected buckets blocked |
| Duplicate channel | Affected bucket blocked |
| Incomplete batch | Affected bucket blocked |
| Zero exposure | Affected bucket blocked |
| Observed zero complaints | Admitted; one downward point alert |

The daily point confusion counts are 50 true positives, 36 false negatives,
0 false positives and 577 true negatives against the fabricated injection labels.
The 36 point misses occur within the sustained-shift episode. The cumulative
detector produces one shift alert and no change alerts outside that injected
episode in this seed. A correct episode alert does not erase point-level misses.

These results demonstrate the intended mechanics on deliberately simple synthetic
inputs. They do not establish real-world accuracy, calibrated error rates,
statistical significance, causal effects or validity of a real complaint exposure
measure. Thresholds were not optimized on this evaluation. Full generated
observations remain in `outputs/signals/evaluation.json` after a run.
