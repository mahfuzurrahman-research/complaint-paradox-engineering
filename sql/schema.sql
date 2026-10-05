CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS mart;

CREATE OR REPLACE TABLE staging.demo_panel AS
SELECT * FROM read_csv_auto($input_path, header = true);

CREATE OR REPLACE VIEW core.panel_observation AS
SELECT
    CAST(entity_id AS VARCHAR) AS entity_id,
    CAST(period_id AS VARCHAR) AS period_id,
    CAST(feature_a AS DOUBLE) AS feature_a,
    CAST(feature_b AS DOUBLE) AS feature_b,
    CAST(outcome_value AS DOUBLE) AS outcome_value
FROM staging.demo_panel;
