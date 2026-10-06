CREATE OR REPLACE TABLE mart.quality_results AS
SELECT * FROM (
    SELECT
        'duplicate_entity_period' AS check_name,
        COUNT(*) AS failure_count
    FROM (
        SELECT entity_id, period_id, COUNT(*) AS n
        FROM core.panel_observation
        GROUP BY entity_id, period_id
        HAVING COUNT(*) > 1
    )

    UNION ALL

    SELECT
        'missing_required_values' AS check_name,
        COUNT(*) AS failure_count
    FROM core.panel_observation
    WHERE entity_id IS NULL
       OR period_id IS NULL
       OR feature_a IS NULL
       OR feature_b IS NULL
       OR outcome_value IS NULL
       OR NOT ISFINITE(feature_a)
       OR NOT ISFINITE(feature_b)
       OR NOT ISFINITE(outcome_value)
       OR TRIM(entity_id) = ''
       OR TRIM(period_id) = ''
       OR entity_id <> TRIM(entity_id)
       OR period_id <> TRIM(period_id)

    UNION ALL

    SELECT
        'feature_a_out_of_range' AS check_name,
        COUNT(*) AS failure_count
    FROM core.panel_observation
    WHERE feature_a < 0 OR feature_a > 1

    UNION ALL

    SELECT
        'feature_b_out_of_range' AS check_name,
        COUNT(*) AS failure_count
    FROM core.panel_observation
    WHERE feature_b < 0 OR feature_b > 1
);
