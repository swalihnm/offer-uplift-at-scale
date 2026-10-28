-- Silver: cleaned rows with user_id, bucket and split.
-- Partitioned by split, so queries on one split only read that split's files.
-- MSCK REPAIR TABLE (run after the write) registers the partition directories.

CREATE EXTERNAL TABLE IF NOT EXISTS oua.silver_criteo (
  f0 DOUBLE, f1 DOUBLE, f2 DOUBLE, f3 DOUBLE,
  f4 DOUBLE, f5 DOUBLE, f6 DOUBLE, f7 DOUBLE,
  f8 DOUBLE, f9 DOUBLE, f10 DOUBLE, f11 DOUBLE,
  treatment INT,
  conversion INT,
  visit INT,
  exposure INT,
  user_id STRING,
  bucket INT
)
PARTITIONED BY (split STRING)
STORED AS PARQUET
LOCATION '${silver_location}';
