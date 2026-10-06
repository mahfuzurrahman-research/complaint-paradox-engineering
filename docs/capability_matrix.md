# Capability-to-Evidence Matrix

| Capability | Public evidence |
|---|---|
| Python engineering | `src/monitoring/`, `src/reporting/` |
| SQL / analytical database | `sql/` |
| Relational modeling | staging/core/mart SQL definitions |
| Data quality | `sql/quality_checks.sql`, monitor checks |
| Automated testing | `tests/` |
| Failure handling | `tests/test_failure_modes.py` |
| Continuous integration | `.github/workflows/public-validation.yml` |
| Containerization | `Dockerfile` |
| Automated reporting | `src/reporting/build_report.py` |
| Static dashboard | `dashboards/build_demo_dashboard.py` |
| Reproducibility | `run_public_demo.sh`, `docs/reproducibility.md` |
| Scientific boundary discipline | `docs/engineering_scope.md` |
| Signal admission and measurement quality | `signal_demo/contracts.py`, `signal_demo/quality.py` |
| Exposure-normalized anomaly detection | `signal_demo/detection.py`, `contracts/signal_contract.json` |
| Stateful change detection | `Cusum`, quality-gap resets and recovery tests in `tests_signal/test_signal.py` |
| Temporal isolation | fixed baseline, availability guard and future-perturbation tests |
| Independent numerical and state validation | `sql/signals.sql`, 26 QA checks in `signal_demo/warehouse.py`, recursive SQL CUSUM |
| Queue completeness and claim boundaries | independent expected alerts, metadata/rank checks and null-safe adverse-action checks |
| Replay and artifact integrity | raw-input semantic replay in `signal_demo/receipts.py`, enforced source manifest and rehashed-corruption tests |
| Publication failure handling | complete staging, stable sibling lock, rename rollback and unknown-file preservation tests |
| Evaluation discipline | separate injection truth, `signal_demo/evaluation.py`, documented misses |
| CV claim provenance | `docs/cv_evidence.md`, `docs/signal_validation_record.md` |

This matrix demonstrates public engineering capability only. It is not evidence of production-industry deployment or independent replication of the private paper.
