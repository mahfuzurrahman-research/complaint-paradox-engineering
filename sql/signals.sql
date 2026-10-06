CREATE SCHEMA IF NOT EXISTS mart;
CREATE TABLE signal_events (
 record_id VARCHAR,area_id VARCHAR,event_day DATE,channel VARCHAR,complaints BIGINT,
 opportunities BIGINT,available_at TIMESTAMPTZ,complete BOOLEAN,synthetic_record BOOLEAN
);
CREATE TABLE signal_schedule (area_id VARCHAR,event_day DATE,monitor_at TIMESTAMPTZ);
CREATE TABLE signal_policy (
 baseline_end DATE,point_limit DOUBLE,max_latency_hours DOUBLE,cusum_k DOUBLE,cusum_h DOUBLE,
 cusum_clip DOUBLE,min_shift_streak INTEGER,recovery_days INTEGER,min_baseline_days INTEGER,
 min_baseline_events INTEGER,reference_id VARCHAR,policy_id VARCHAR
);
CREATE TABLE signal_quality (
 area_id VARCHAR,event_day DATE,monitor_at TIMESTAMPTZ,admitted BOOLEAN,
 reason_codes VARCHAR,complaints BIGINT,opportunities BIGINT
);
CREATE TABLE signal_reference (
 area_id VARCHAR,channel VARCHAR,rate DOUBLE,dispersion DOUBLE,mean_exposure DOUBLE,baseline_days INTEGER
);
CREATE TABLE signal_monitor (
 area_id VARCHAR,event_day DATE,admitted BOOLEAN,expected_count DOUBLE,expected_variance DOUBLE,
 standardized_residual DOUBLE,point_alert BOOLEAN,change_alert BOOLEAN,reference_id VARCHAR,
 change_direction VARCHAR,cusum_up DOUBLE,cusum_down DOUBLE,rate_per_1000 DOUBLE,
 exposure_ratio DOUBLE,state_reset BOOLEAN,policy_id VARCHAR
);
CREATE TABLE signal_review (
 queue_rank INTEGER,alert_id VARCHAR,area_id VARCHAR,event_day DATE,alert_type VARCHAR,
 priority INTEGER,standardized_residual DOUBLE,reference_id VARCHAR,policy_id VARCHAR,
 reason_codes VARCHAR,review_status VARCHAR,recommended_action VARCHAR,adverse_action_authorized BOOLEAN
);

-- RECONSTRUCT AFTER LOADING
CREATE TABLE mart.signal_raw_quality AS
WITH counts AS (
 SELECT s.area_id,s.event_day,s.monitor_at,count(e.record_id) n,
 count(*) FILTER(WHERE e.channel='mobile') n_mobile,
 count(*) FILTER(WHERE e.channel='legacy') n_legacy,
 count(*) FILTER(WHERE NOT e.complete) incomplete,
 count(*) FILTER(WHERE e.opportunities=0) zero_exposure,
 count(*) FILTER(WHERE e.available_at>s.monitor_at) unavailable,
 count(*) FILTER(WHERE e.available_at>CAST(s.event_day+1 AS TIMESTAMPTZ)+p.max_latency_hours*INTERVAL '1 hour') late,
 sum(e.complaints)::BIGINT complaints,sum(e.opportunities)::BIGINT opportunities
 FROM signal_schedule s CROSS JOIN signal_policy p
 LEFT JOIN signal_events e USING(area_id,event_day) GROUP BY s.area_id,s.event_day,s.monitor_at
)
SELECT *,n_mobile=1 AND n_legacy=1 AND incomplete=0 AND zero_exposure=0 AND unavailable=0 AND late=0 admitted,
to_json(list_filter([
 CASE WHEN n_mobile>1 OR n_legacy>1 THEN 'DUPLICATE_CHANNEL' END,
 CASE WHEN incomplete>0 THEN 'INCOMPLETE_BATCH' END,
 CASE WHEN late>0 THEN 'LATE_BATCH' END,
 CASE WHEN n_mobile=0 OR n_legacy=0 THEN 'MISSING_CHANNEL' END,
 CASE WHEN unavailable>0 THEN 'UNAVAILABLE_AT_MONITOR' END,
 CASE WHEN zero_exposure>0 THEN 'ZERO_EXPOSURE' END
],x->x IS NOT NULL))::VARCHAR reason_codes FROM counts;

CREATE TABLE mart.signal_baseline AS
WITH totals AS (
 SELECT e.area_id,e.channel,sum(e.complaints) events,sum(e.complaints)::DOUBLE/sum(e.opportunities) rate,
 avg(e.opportunities)::DOUBLE mean_exposure,count(*)::INTEGER baseline_days
 FROM signal_events e JOIN mart.signal_raw_quality q USING(area_id,event_day) CROSS JOIN signal_policy p
 WHERE q.admitted AND e.event_day<=p.baseline_end GROUP BY e.area_id,e.channel
)
-- Floating sums use declared order so independent replays agree exactly.
SELECT t.*,greatest(1.0,sum(pow(e.complaints-t.rate*e.opportunities,2)/greatest(t.rate*e.opportunities,1.0) ORDER BY e.event_day,e.record_id)/(t.baseline_days-1)) dispersion
FROM totals t JOIN signal_events e USING(area_id,channel)
JOIN mart.signal_raw_quality q USING(area_id,event_day) CROSS JOIN signal_policy p
WHERE q.admitted AND e.event_day<=p.baseline_end
GROUP BY t.area_id,t.channel,t.events,t.rate,t.mean_exposure,t.baseline_days;

CREATE TABLE mart.signal_expectation AS
SELECT e.area_id,e.event_day,sum(e.complaints)::BIGINT complaints,sum(e.opportunities)::BIGINT opportunities,
 sum(e.opportunities*r.rate ORDER BY e.channel) expected_count,
 sum(e.opportunities*r.rate*r.dispersion ORDER BY e.channel) expected_variance,
 sum(r.mean_exposure ORDER BY e.channel) training_exposure
FROM signal_events e JOIN mart.signal_raw_quality q USING(area_id,event_day)
JOIN mart.signal_baseline r USING(area_id,channel) WHERE q.admitted GROUP BY e.area_id,e.event_day;

CREATE TABLE mart.signal_sql_scored AS
SELECT q.area_id,q.event_day,q.admitted,q.reason_codes,
 CASE WHEN q.admitted THEN x.expected_count END expected_count,
 CASE WHEN q.admitted THEN x.expected_variance END expected_variance,
 CASE WHEN q.admitted THEN (q.complaints-x.expected_count)/sqrt(greatest(x.expected_variance,1.0)) END z,
 CASE WHEN q.admitted THEN q.complaints::DOUBLE/q.opportunities*1000 END rate_per_1000,
 CASE WHEN q.admitted THEN q.opportunities/x.training_exposure END exposure_ratio
FROM mart.signal_raw_quality q LEFT JOIN mart.signal_expectation x USING(area_id,event_day)
CROSS JOIN signal_policy p WHERE q.event_day>p.baseline_end;

-- Independent recursive implementation of the declared clipped, streak-gated, latched CUSUM.
CREATE TABLE mart.signal_sql_cusum AS
WITH RECURSIVE ordered AS (
 SELECT s.*,row_number() OVER(PARTITION BY area_id ORDER BY event_day) idx,
 greatest(-p.cusum_clip,least(p.cusum_clip,s.z)) clipped FROM mart.signal_sql_scored s CROSS JOIN signal_policy p
), walk(area_id,idx,up,down,up_streak,down_streak,recovery_streak,latched,direction) AS (
 SELECT DISTINCT area_id,0::BIGINT,0::DOUBLE,0::DOUBLE,0::INTEGER,0::INTEGER,0::INTEGER,NULL::VARCHAR,NULL::VARCHAR FROM signal_schedule
 UNION ALL
 SELECT s.area_id,s.idx,b.up,b.down,b.us,b.ds,b.rs,coalesce(b.latched,d.direction),d.direction
 FROM walk w JOIN ordered s ON s.area_id=w.area_id AND s.idx=w.idx+1 CROSS JOIN signal_policy p
 CROSS JOIN LATERAL (
   SELECT greatest(0.0,w.up+s.clipped-p.cusum_k) up,greatest(0.0,w.down-s.clipped-p.cusum_k) down,
   CASE WHEN s.z>p.cusum_k THEN w.up_streak+1 ELSE 0 END us,
   CASE WHEN s.z< -p.cusum_k THEN w.down_streak+1 ELSE 0 END ds,
   CASE WHEN abs(s.z)<=p.cusum_k THEN w.recovery_streak+1 ELSE 0 END rs
 ) a
 CROSS JOIN LATERAL (SELECT NOT s.admitted OR (w.latched IS NOT NULL AND a.rs>=p.recovery_days) AS should_reset) resetter
 CROSS JOIN LATERAL (
   SELECT CASE WHEN should_reset THEN 0.0 ELSE a.up END up,CASE WHEN should_reset THEN 0.0 ELSE a.down END down,
   CASE WHEN should_reset THEN 0 ELSE a.us END us,CASE WHEN should_reset THEN 0 ELSE a.ds END ds,
   CASE WHEN should_reset THEN 0 ELSE a.rs END rs,CASE WHEN should_reset THEN NULL ELSE w.latched END latched
 ) b
 CROSS JOIN LATERAL (
   SELECT CASE WHEN b.latched IS NULL AND s.admitted AND b.up>=p.cusum_h AND b.us>=p.min_shift_streak THEN 'UP'
     WHEN b.latched IS NULL AND s.admitted AND b.down>=p.cusum_h AND b.ds>=p.min_shift_streak THEN 'DOWN' END direction
 ) d
)
SELECT s.area_id,s.event_day,w.up,w.down,w.direction FROM ordered s JOIN walk w USING(area_id,idx);

CREATE TABLE mart.signal_expected_review AS
WITH candidates AS (
 SELECT s.area_id,s.event_day,'SIGNAL_QUALITY' alert_type,3 priority,s.z,
  s.reason_codes,'CHECK_FEED' recommended_action FROM mart.signal_sql_scored s WHERE NOT s.admitted
 UNION ALL SELECT s.area_id,s.event_day,'RATE_SHIFT_ALERT',2,s.z,'["CUSUM_SHIFT_ALERT"]','REVIEW_SIGNAL_AND_CONTEXT'
 FROM mart.signal_sql_scored s JOIN mart.signal_sql_cusum c USING(area_id,event_day) WHERE c.direction IS NOT NULL
 UNION ALL SELECT s.area_id,s.event_day,'POINT_ANOMALY',1,s.z,'["POINT_LIMIT_EXCEEDED"]','REVIEW_SIGNAL_AND_CONTEXT'
 FROM mart.signal_sql_scored s CROSS JOIN signal_policy p WHERE s.admitted AND abs(s.z)>=p.point_limit
)
SELECT row_number() OVER(ORDER BY priority DESC,abs(coalesce(z,0)) DESC,event_day,area_id,alert_type) queue_rank,
 area_id||':'||event_day::VARCHAR||':'||alert_type alert_id,c.*,p.reference_id,p.policy_id
FROM candidates c CROSS JOIN signal_policy p;

CREATE VIEW mart.signal_alerts AS SELECT * FROM signal_review ORDER BY queue_rank;
CREATE VIEW mart.signal_coverage AS SELECT event_day,count(*) expected_buckets,
 count(*) FILTER(WHERE admitted) admitted_buckets,count(*) FILTER(WHERE NOT admitted) blocked_buckets
FROM signal_quality GROUP BY event_day ORDER BY event_day;
