-- Bronze: raw Criteo rows as Parquet, registered as an EXTERNAL table.
-- The data stays where it is written, and dropping the table leaves the files in place.
-- ${bronze_location} is filled in by oua.spark.run_hql.

CREATE DATABASE IF NOT EXISTS oua;

CREATE EXTERNAL TABLE IF NOT EXISTS oua.bronze_criteo (
  f0 DOUBLE, f1 DOUBLE, f2 DOUBLE, f3 DOUBLE,
  f4 DOUBLE, f5 DOUBLE, f6 DOUBLE, f7 DOUBLE,
  f8 DOUBLE, f9 DOUBLE, f10 DOUBLE, f11 DOUBLE,
  treatment INT,
  conversion INT,
  visit INT,
  exposure INT
)
STORED AS PARQUET
LOCATION '${bronze_location}';
