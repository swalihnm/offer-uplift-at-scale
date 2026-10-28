# Methods

This describes what the code does. Each step names the module that implements it.

## 1. Data lake (`oua.ingest`, `oua.lake`, `sql/hive/`)

- **Bronze:** the raw CSV.gz is read with an explicit schema (12 double features, four integer flags) and written as Parquet. It is registered as the external Hive table `oua.bronze_criteo`. The raw file's SHA-256 is checked on every run.
- **Silver:** rows with a null outcome are dropped (none exist in this file). Identical rows are kept as separate users, and each repeat gets an occurrence index, so `user_id = sha256(all columns | occurrence)` is unique. Each row gets a `bucket` (CRC32 of `user_id` mod 100) and a `split`.
- **Split:** the split is stratified by treatment × visit. Within each stratum, rows are ranked by `user_id` and cut at 70% / 85%, so the shares are exact per stratum. Silver is partitioned by `split`, so queries on one split read only that split's files.
- **Gold (HiveQL):** `gold_experiment_summary` (counts and rates by arm), `gold_balance_check` (mean and sample standard deviation of each feature by arm, via `STACK`), `gold_bucket_metrics` (counts and sums by bucket and arm).
- **DQ checks:** bronze row count equals the source line count minus the header; no null outcomes; treated share within 0.02 of 0.85; split counts sum to silver.

## 2. Experiment analysis (`oua.ab_test`)

- **Balance:** standardized mean difference per feature, using the pooled SD. A clean randomization at this sample size would give SMDs near 0.001, so the threshold of 0.1 in the spec is a weak check here.
- **Sample ratio mismatch:** chi-square goodness-of-fit of treated and control counts against 85/15.
- **ATE:** intent-to-treat difference in two proportions. The z-test uses the pooled SE; the CI uses the unpooled SE. A cross-check uses a bucket bootstrap: 100 hash buckets, resampled 2,000 times.
- **CUPED:** a pooled least-squares fit of the outcome on the 12 features, on a random sample of about 2M rows, ignoring treatment. The adjusted outcome is `y − (β·x − mean)`. Variance reduction is the drop in outcome variance.
- **Power:** minimum detectable absolute and relative lift at 80% power and two-sided 5%, for 100K, 1M and the full population, at 50/50 and 85/15.
- **Exposure:** intent-to-treat against exposed-only, to show the selection gap.

## 3. Uplift models (`oua.uplift`)

- **Training data:** a stratified sample of 1.5M rows from the train split, stratified by treatment × visit.
- **Learners** (LightGBM, same hyperparameters for all):
  - S-learner: one classifier on features plus treatment; uplift = P(visit | x, T=1) − P(visit | x, T=0).
  - T-learner: one classifier per arm; uplift = difference of the two predictions.
  - Class transformation: regression on Z = YT/π + (1−Y)(1−T)/(1−π); uplift = E[Z|x] − 1. π is the treated share in the training sample.
  - X-learner: T-learner imputed effects, one regression per arm, blended with π.
- **Selection:** the learner with the highest Qini AUC on the valid split is selected. Test results are reported for all learners.
- **Qini AUC:** area between the model's cumulative incremental-visit curve and the random-targeting line.
- **Deciles:** test rows sorted by predicted uplift and split into ten equal groups. Observed lift is the treated mean minus the control mean within each group.
- **Segments:** do-not-disturb if predicted uplift < 0; otherwise persuadable if uplift ≥ the median; otherwise sure thing if baseline ≥ the median baseline; otherwise lost cause. The baseline is a classifier trained on control only.
- **SHAP:** mean absolute SHAP of the uplift, computed as the difference of the two T-learner models' SHAP values on 5,000 test rows.
- **Tracking:** each learner is logged to a local MLflow file store.

## 4. ROI and targeting (`oua.roi`)

- **Cutoff:** the profit-maximising share on a 0.5% grid, computed on the valid split with the base economics. Test profit is reported at that cutoff.
- **Policies:** target nobody; target everyone; a seeded random 30%; top-k by predicted uplift at the valid cutoff.
- **Economics:** for a targeted share `s`, customers = `s × N`. Incremental visits = customers × lift, where lift is the treated minus control difference inside the targeted set. Cost = customers × cost per treated. Value = visits × value per visit + conversions × value per conversion. ROI = (value − cost) / cost.
- **Budget curve:** the same economics at each grid point, computed with cumulative sums over the uplift-sorted rows.
- **Sensitivity:** the cutoff is re-chosen on the valid split for each cost × conversion-value pair, and its test profit is reported.

## 5. BigQuery (`oua.bq_load`, `oua.bq_queries`, `sql/bigquery/`)

- The nine result tables are loaded into `offer_uplift` with truncate-on-load, from the CSV extracts.
- Four analysis queries run against those tables: decile lift, cumulative gain (window functions over deciles), policy ranking (window RANK), and segment waste.

## Tests (`tests/`)

- `test_stats.py` (13 tests, pure Python): z-test against a hand calculation; SMD; SRM; power/MDE scaling; CUPED never increases variance; random Qini near zero; a perfect model beats random; segment assignment; ROI identities (target nobody costs nothing; target everyone equals ATE × N); the fast budget curve matches the direct calculation.
- `test_silver.py` (3 tests, Spark): exact duplicates are kept as separate users and null outcomes are dropped; the split is exact within each stratum; a small expected frame.
