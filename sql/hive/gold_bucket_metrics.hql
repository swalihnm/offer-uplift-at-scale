-- Gold: counts and outcome sums by hash bucket x treatment.
-- Used for bucket-level variance estimates and bootstrap in ab_test.py.

DROP TABLE IF EXISTS oua.gold_bucket_metrics;

CREATE TABLE oua.gold_bucket_metrics STORED AS PARQUET AS
SELECT
  bucket,
  treatment,
  COUNT(*)        AS n,
  SUM(visit)      AS visits,
  SUM(conversion) AS conversions
FROM oua.silver_criteo
GROUP BY bucket, treatment;
