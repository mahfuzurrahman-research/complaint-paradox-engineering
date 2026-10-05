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

This matrix demonstrates public engineering capability only. It is not evidence of production-industry deployment or independent replication of the private paper.
