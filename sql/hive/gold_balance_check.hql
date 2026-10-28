-- Gold: mean and sample standard deviation of each feature, per treatment group.
-- Standardized mean differences (SMD) are computed from this table in ab_test.py.
-- Wide aggregates first, then STACK turns them into one row per (group, feature).

DROP TABLE IF EXISTS oua.gold_balance_check;

CREATE TABLE oua.gold_balance_check STORED AS PARQUET AS
SELECT a.treatment, b.feature, b.mean_val, b.sd_val
FROM (
  SELECT
    treatment,
    AVG(f0)  AS m0,  STDDEV_SAMP(f0)  AS s0,
    AVG(f1)  AS m1,  STDDEV_SAMP(f1)  AS s1,
    AVG(f2)  AS m2,  STDDEV_SAMP(f2)  AS s2,
    AVG(f3)  AS m3,  STDDEV_SAMP(f3)  AS s3,
    AVG(f4)  AS m4,  STDDEV_SAMP(f4)  AS s4,
    AVG(f5)  AS m5,  STDDEV_SAMP(f5)  AS s5,
    AVG(f6)  AS m6,  STDDEV_SAMP(f6)  AS s6,
    AVG(f7)  AS m7,  STDDEV_SAMP(f7)  AS s7,
    AVG(f8)  AS m8,  STDDEV_SAMP(f8)  AS s8,
    AVG(f9)  AS m9,  STDDEV_SAMP(f9)  AS s9,
    AVG(f10) AS m10, STDDEV_SAMP(f10) AS s10,
    AVG(f11) AS m11, STDDEV_SAMP(f11) AS s11
  FROM oua.silver_criteo
  GROUP BY treatment
) a
LATERAL VIEW STACK(12,
  'f0',  a.m0,  a.s0,
  'f1',  a.m1,  a.s1,
  'f2',  a.m2,  a.s2,
  'f3',  a.m3,  a.s3,
  'f4',  a.m4,  a.s4,
  'f5',  a.m5,  a.s5,
  'f6',  a.m6,  a.s6,
  'f7',  a.m7,  a.s7,
  'f8',  a.m8,  a.s8,
  'f9',  a.m9,  a.s9,
  'f10', a.m10, a.s10,
  'f11', a.m11, a.s11
) b AS feature, mean_val, sd_val;
