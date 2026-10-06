# Observed local validation

Validated on 2026-10-06 UTC using Python 3.12.14 on Linux, NumPy 2.3.5,
DuckDB 1.5.6 and pytest 9.1.1. These are actual local observations from
the original demo, `python -m pytest -q tests tests_signal`, signal generation and
`--verify-only`, not results from a hosted CI or Docker run.

## Execution and integrity

| Check | Observed result |
|---|---|
| Original synthetic panel, SQL, reports and dashboard | PASS |
| Original tests | 14 passed |
| Signal tests | 110 passed |
| Total local tests | 124 passed; no skipped tests |
| Signal pipeline and receipt verification | PASS |
| Independent DuckDB checks | 26 signal + 4 original checks, zero failures |
| Saved-reference replay | Identical scores and queue |
| Repeated runs | Identical data CSV/JSON files and manifest |
| Future perturbation | Baseline and earlier scores unchanged |
| Corruption/incomplete receipt | Rejected |
| Changed artifacts with rewritten hashes | Rejected by semantic replay |
| Current source/manifest mismatch | Rejected |
| Missing/null/corrupted SQL scores | Rejected |
| Missing/extra queue alerts and null action flags | Rejected |
| CUSUM state, direction, recovery and gap parity | PASS; corrupt states rejected |
| Coherently rehashed but incorrect references | Rejected against raw baseline |
| Staging failure | Previous completed output preserved |
| Publication rename failure | Previous completed output restored |
| Concurrent writer | Rejected; lock released after failure |
| Parent-path alias writer | Rejected by the same stable lock |
| Replay without undeclared `pytz` | PASS in subprocess with imports blocked |
| Unknown output files and symlinks | Refused and preserved |
| Dependency compatibility | `python -m pip check` passed |

Docker was unavailable locally. For baseline commit `26b9e51`, the
[second hosted attempt](https://github.com/mahfuzurrahman-research/complaint-paradox-engineering/actions/runs/37372191880/attempts/2)
passed, including Docker build/execution and artifact upload. The first attempt
was cancelled with no assigned runner or executed steps. This establishes the
baseline's hosted result, not the repaired revision's result. The
[workflow page](https://github.com/mahfuzurrahman-research/complaint-paradox-engineering/actions/workflows/public-validation.yml)
records the tested commit and result for every revision; inspect the matching
commit before claiming hosted CI or Docker success. See the repair record for
the separate validation defects addressed here.

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
