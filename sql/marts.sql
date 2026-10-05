CREATE OR REPLACE VIEW mart.period_summary AS
SELECT
    period_id,
    COUNT(*) AS n,
    AVG(feature_a) AS mean_feature_a,
    AVG(feature_b) AS mean_feature_b,
    AVG(outcome_value) AS mean_outcome
FROM core.panel_observation
GROUP BY period_id
ORDER BY period_id;

CREATE OR REPLACE VIEW mart.entity_summary AS
SELECT
    entity_id,
    COUNT(*) AS n_periods,
    AVG(outcome_value) AS mean_outcome
FROM core.panel_observation
GROUP BY entity_id
ORDER BY entity_id;
