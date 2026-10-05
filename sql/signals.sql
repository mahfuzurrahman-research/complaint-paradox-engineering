CREATE SCHEMA IF NOT EXISTS mart;

CREATE TABLE signal_events (
  record_id VARCHAR, area_id VARCHAR, event_day DATE, channel VARCHAR,
  complaints BIGINT, opportunities BIGINT, available_at TIMESTAMPTZ,
  complete BOOLEAN, synthetic_record BOOLEAN
);
CREATE TABLE signal_quality (
  area_id VARCHAR, event_day DATE, monitor_at TIMESTAMPTZ,
  admitted BOOLEAN, reason_codes VARCHAR, complaints BIGINT, opportunities BIGINT
);
CREATE TABLE signal_reference (
  area_id VARCHAR, channel VARCHAR, rate DOUBLE,
  dispersion DOUBLE, mean_exposure DOUBLE
);
CREATE TABLE signal_monitor (
  area_id VARCHAR, event_day DATE, admitted BOOLEAN, expected_count DOUBLE,
  expected_variance DOUBLE, standardized_residual DOUBLE,
  point_alert BOOLEAN, change_alert BOOLEAN, reference_id VARCHAR
);
CREATE TABLE signal_review (
  alert_id VARCHAR, area_id VARCHAR, event_day DATE, alert_type VARCHAR,
  priority INTEGER, review_status VARCHAR, adverse_action_authorized BOOLEAN
);

CREATE VIEW mart.signal_expectation AS
SELECT e.area_id, e.event_day,
       SUM(e.complaints)::BIGINT AS complaints,
       SUM(e.opportunities)::BIGINT AS opportunities,
       SUM(e.opportunities * r.rate) AS expected_count,
       SUM(e.opportunities * r.rate * r.dispersion) AS expected_variance
FROM signal_events e
JOIN signal_quality q USING (area_id, event_day)
JOIN signal_reference r USING (area_id, channel)
WHERE q.admitted
GROUP BY e.area_id, e.event_day;

CREATE VIEW mart.signal_alerts AS
SELECT * FROM signal_review ORDER BY priority DESC, event_day, area_id, alert_type;

CREATE VIEW mart.signal_coverage AS
SELECT event_day, COUNT(*) AS expected_buckets,
       SUM(CASE WHEN admitted THEN 1 ELSE 0 END) AS admitted_buckets,
       SUM(CASE WHEN NOT admitted THEN 1 ELSE 0 END) AS blocked_buckets
FROM signal_quality GROUP BY event_day ORDER BY event_day;
