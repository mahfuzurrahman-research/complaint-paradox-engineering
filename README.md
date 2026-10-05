# Complaint Paradox — Public Engineering Companion

**Public-safe research engineering portfolio by Mahfuzur Rahman**

This repository demonstrates the software and data-engineering practices used around a private research project on administrative observability and complaint-based performance measurement. It is intentionally separated from the private scientific repository.

The purpose is to make engineering capability independently inspectable **without publishing the manuscript, real analytical datasets, exact empirical specification, private results, bootstrap outputs, or restricted provenance**.

## What this public companion demonstrates

- Python-based input monitoring and automated reporting
- SQL / DuckDB analytical modeling
- synthetic-data pipeline design
- schema, uniqueness, missingness and range checks
- deterministic machine-readable outputs
- unit and failure-mode tests
- GitHub Actions continuous integration
- bounded Docker execution
- public-safe static dashboard generation
- explicit separation between engineering verification and scientific claims

## Public architecture

```text
Synthetic demo panel
        │
        ▼
Input monitoring
        │
        ▼
DuckDB staging / core / marts
        │
        ▼
Relational quality checks
        │
        ▼
Automated tests
        │
        ▼
JSON + Markdown reporting
        │
        ▼
Static HTML dashboard
        │
        ▼
GitHub Actions / Docker
```

## Repository map

```text
.
├── data/synthetic/              # deterministic synthetic demo data only
├── src/monitoring/              # public-safe validation code
├── src/reporting/               # public-safe report generation
├── sql/                         # DuckDB schema, marts and QA checks
├── tests/                       # unit, integration and failure-mode tests
├── dashboards/                  # static demo dashboard builder
├── examples/                    # small analytical demonstration
├── docs/                        # architecture, QA, scope and reproducibility
├── .github/workflows/           # continuous integration
├── Dockerfile
└── run_public_demo.sh
```

## Quick start

Requirements: Python 3.12+.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
bash run_public_demo.sh
```

The run creates only public-safe outputs under `outputs/`.

## Engineering boundary

This repository is **not** the scientific replication package for the private Complaint Paradox paper. It intentionally contains no pathway for reconstructing the private empirical study.

It does not contain:

- manuscript text;
- canonical analytical datasets;
- real research rows or disguised subsets;
- exact private variable construction;
- exact unpublished model specification;
- empirical coefficients, p-values or bootstrap results;
- private execution logs or seed manifests;
- restricted provenance or journal-review material.

The synthetic data were generated specifically for this companion and are not derived row-by-row from the private research data.

## Capability matrix

See [`docs/capability_matrix.md`](docs/capability_matrix.md).

## Reproducibility

See [`docs/reproducibility.md`](docs/reproducibility.md).

## Copyright and reuse

Copyright © 2026 Mahfuzur Rahman. All rights reserved.

No open-source license is granted by this repository. See [`COPYRIGHT.md`](COPYRIGHT.md).
