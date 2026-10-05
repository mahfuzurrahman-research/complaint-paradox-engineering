# Supported CV evidence

The public code supports this project description:

> Engineered a synthetic complaint-signal monitoring pipeline in Python and
> DuckDB with completeness and availability checks, channel-specific exposure
> normalization, point-anomaly detection, stateful CUSUM change alerts, and
> temporally isolated validation.

A more compact skills-oriented bullet:

> Built and tested signal-quality, anomaly and change-detection workflows using
> fabricated complaint streams, independent SQL checks and reproducible artifacts.

| Claim | Inspectable evidence |
|---|---|
| Signal-quality engineering | schema contract, scheduled inventory, blocked buckets and valid-zero tests |
| Statistical anomaly/change detection | working-variance residuals and modified two-sided CUSUM |
| Temporal validation | earlier-only fitting, availability guards and future-perturbation tests |
| Numerical verification | DuckDB independently recomputes rates, totals and scores |
| Reproducible engineering | fixed seed/policy, saved reference replay, source/dependency manifest |
| Testing | local suite and failure/corruption checks; see validation record |
| CI/container configuration | workflow and Dockerfile; hosted execution requires a completed passing run |

The project does not substantiate production deployment, real administrative
data experience, real-world predictive accuracy, causal evaluation or replication
of the private scientific findings. It uses statistical detection, not a trained
machine-learning classifier. Synthetic counts and validation metrics must retain
their synthetic label in CV or interview discussion. The validation record reports
point misses as well as detections; successful change detection is not equivalent
to perfect bucket-level anomaly classification.
