# Signal quality, point anomalies and sustained changes

This module demonstrates monitoring of reported complaints using independently
fabricated inputs. Its exposure field means fabricated active reporting
opportunities. It does not measure the latent number of service failures. An
increase in reporting access can increase complaints without increasing the
underlying failure rate; the detector therefore models channel-specific reporting
rates rather than treating every increase in raw complaints as deterioration.

## Admission and chronology

The scheduled inventory has six fabricated areas, two channels and 168 days.
Records require exact fields, unique neutral record IDs, non-negative integer
counts, canonical UTC timestamps and explicit synthetic/completeness markers.
Injection labels and unknown fields are rejected from operational records.

Each daily bucket requires both channels exactly once, positive exposures and
complete records available by 07:00 UTC the following day. The maximum permitted
arrival lag is 12 hours after period end; availability at the 07:00 deadline is
allowed. The default generator arrives at 06:00. Records cannot claim completed
daily counts before that day ends.

An absent channel or entire day remains a scheduled blocked bucket with null
counts and scores. Incomplete, duplicate, future and late records also block the
bucket and reset cumulative state. A complete bucket with observed zero counts
and positive exposure is admitted and scored. Later arrivals do not backfill an
earlier score in this monitoring reconstruction. Availability metadata is used
to exclude records that would not have been available at the decision time;
their future values never contribute to that decision's score.

The reference uses only the first 56 days, requires an entirely admitted baseline,
at least 28 observations per area and at least 20 events per channel. Missing
baseline data causes a failure rather than silent selection or imputation. The
reference records the latest baseline availability, input hash and full policy.
It must be available before a monitoring origin. It stays frozen for the later
112 days; no monitoring labels or future counts enter fitting.

## Expected counts and point alerts

For area/channel j, the baseline rate is `r_j = sum(count_j) / sum(exposure_j)`.
The working dispersion is the Pearson-style residual sum divided by `n-1`,
floored at one. For a later bucket:

```
expected_count = sum(r_j * current_exposure_j)
expected_variance = sum(dispersion_j * r_j * current_exposure_j)
z = (observed_count - expected_count) / sqrt(max(expected_variance, 1))
```

The point threshold is `abs(z) >= 4`. This is a heuristic score using a
Poisson-style working variance. It ignores uncertainty in the fitted rates,
serial dependence and cross-channel covariance; it is not a p-value or a
calibrated probability. Small expected counts, changing measurement definitions
and invalid denominators require further method development.

An exposure change at a constant reporting rate changes expected counts. The
demo also compares a naive baseline raw-count rule to show why that distinction
matters. Normalization alone cannot separate access, willingness to complain,
population composition, service demand and underlying service quality.

## Modified CUSUM

The recurrence follows the two-sided tabular structure described in the
[NIST CUSUM handbook](https://www.itl.nist.gov/div898/handbook/pmc/section3/pmc323.htm).
This implementation deliberately modifies it with clipping, streak gates,
episode latching, recovery and quality-gap resets:

```
w = clip(z, -3, 3)
up = max(0, up + w - 0.5)
down = max(0, down - w - 0.5)
```

An alert requires a cumulative value of at least 8 and at least three consecutive
residuals beyond `+0.5` or `-0.5` in the matching direction. A single large spike
can contribute at most 2.5 to a freshly reset accumulator. After a change alert,
the episode latches and suppresses further change alerts, including opposite
direction alerts, until five consecutive residuals satisfy `abs(z) <= 0.5` or a
blocked bucket resets state. Point alerts remain relative to the frozen baseline
and can recur during a sustained shift.

These thresholds were specified before the default injection evaluation. No
average-run-length calibration, general false-alarm bound or optimal change-point
claim is made. Seasonality, baseline drift and multiple comparisons are not
modeled. A historical reference may become stale; the demo has no automatic
refitting or production incident lifecycle.

## Review, evaluation and integrity

The queue prioritizes feed-quality review, then change review, then point review.
This ordering is an explicit demo policy, not a learned severity ranking. IDs,
reasons, policy/reference versions and pending status support an audit. Every row
sets `adverse_action_authorized=false`. Ground truth is supplied only to the
offline evaluator after scoring. Daily point confusion and event-level change
delay are separate quantities; repeated point misses within a shifted episode
are retained in the evaluation.

DuckDB independently recomputes baseline rates, count/exposure totals, expected
counts, variances and standardized residuals. Additional checks cover monitor
inventory, null/non-finite admitted scores, blocked scores, duplicate keys and
unauthorized actions. Saved-reference replay must reproduce scores and queue.
Output hashes detect file inconsistency; they do not authenticate the producer.
