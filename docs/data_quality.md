# Data-Quality Controls

The synthetic demonstration pipeline checks:

1. required columns exist;
2. the composite key `(entity_id, period_id)` is unique;
3. identifiers are non-empty;
4. numeric fields are finite and non-missing;
5. `feature_a` and `feature_b` lie within their declared synthetic ranges;
6. the expected synthetic panel dimensions are preserved;
7. SQL quality checks return zero failures.

The controls are intentionally generic. They do not encode the private study's canonical sample identities, real dimensions, hashes, variable definitions, or scientific thresholds.
