-- Gold: outcome rates by treatment group, over all rows (intent-to-treat).

DROP TABLE IF EXISTS oua.gold_experiment_summary;

CREATE TABLE oua.gold_experiment_summary STORED AS PARQUET AS
SELECT
  treatment,
  COUNT(*)        AS n,
  SUM(visit)      AS visits,
  SUM(conversion) AS conversions,
  SUM(exposure)   AS exposed,
  AVG(visit)      AS visit_rate,
  AVG(conversion) AS conversion_rate,
  AVG(exposure)   AS exposure_rate
FROM oua.silver_criteo
GROUP BY treatment;
