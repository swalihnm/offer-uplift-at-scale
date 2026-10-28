# Offer Uplift at Scale

Which customers should get a marketing offer? This project measures the incremental effect of an offer on the Criteo Uplift v2.1 randomized experiment (13,979,592 customers, 85% treated), finds who the offer persuades with uplift models, and turns that into an ROI and targeting decision.

**Status:** the analysis pipeline runs end to end and every number below comes from its output (see `outputs/metrics/`). The results are also loaded into BigQuery. Only the Tableau Public workbook is left, and it needs Tableau Desktop. See [Remaining work](#remaining-work).

## Key findings

1. **The offer raises visits by +1.03 percentage points** (3.82% → 4.85%, 95% CI +1.01 to +1.06 pp, +27% relative). Conversions rise by +0.12 pp (CI +0.11 to +0.12 pp, +59% relative). This is the raw intent-to-treat estimate, the headline number.
2. **CUPED cuts outcome variance by 28%, but it moves the estimate to +0.70 pp (CI +0.67 to +0.72 pp).** The two intervals don't overlap. The gap is exactly the covariate imbalance term β·(x̄_treated − x̄_control), so CUPED is correct. The imbalance itself is still unexplained (see [limitations](docs/limitations.md), item 1). The raw estimate is the headline.
3. **Targeting by predicted uplift works.** The S-learner's test Qini AUC is 6,843 against 19 for random targeting. Its top decile shows a 6.2 pp lift, 6.0× the average. The other learners were weaker: T-learner 5,229, X-learner 3,560. The class-transformation learner failed (see [limitations](docs/limitations.md), item 6).
4. **Targeting everyone loses money at the assumed economics; targeting the top 23% by uplift makes a profit.** At $0.05 per customer and $40 per conversion, targeting everyone gives profit −$16.9k (ROI −2.4%). The cutoff is chosen on the valid split (23%), then reported on test: profit +$398k, ROI 248%. Targeting the top 20% keeps 80% of the incremental conversions at 20% of the cost.
5. **Sure things and lost causes take 42% of the spend under target-everyone.** Sure things are 4.1% of customers, lost causes 38.3%. The result holds across the cost and value grid: the valid-chosen cutoff ranges from 11.5% to 31%, and test profit is positive at that cutoff in all 9 settings. Targeting everyone is unprofitable in 5 of the 9.

The cost and value figures are placeholder assumptions in [conf/economics.yaml](conf/economics.yaml). The sensitivity grid is there because the decision depends on them.

## Data

- **Source:** Criteo AI Lab, Criteo Uplift Prediction Dataset v2.1 (download details and checksum in [docs/data.md](docs/data.md)).
- **Rows:** 13,979,592, one per customer. Treated share 85.0%.
- **Features:** `f0`–`f11`, anonymized. Outcomes: `visit` (main) and `conversion`.
- **Duplicates:** 1,259,545 rows are exact repeats of another row. They are kept as separate users, because dropping them broke the randomization. The repeats are 95.7% treated and contain 42 visits in total, which looks like a logging artifact. Unique rows alone give a visit lift of +1.91 pp, against +1.03 pp for all rows (see [limitations](docs/limitations.md), item 2).

## Results

### Experiment (intent-to-treat)

| Outcome | Control | Treated | Lift | 95% CI | p |
|---|---|---|---|---|---|
| Visit | 3.82% | 4.85% | +1.03 pp (+27%) | +1.01 to +1.06 pp | < 1e-16 |
| Conversion | 0.194% | 0.309% | +0.12 pp (+59%) | +0.11 to +0.12 pp | 7e-179 |

- **Randomization:** SRM passes (treated share 85.0000%, p = 0.999). Max |SMD| across the 12 features is 0.049, with none at or above 0.1. Imbalance is still beyond chance; see [limitations](docs/limitations.md), item 1.
- **Bucket bootstrap** (100 hash buckets) agrees with the analytic CI: +1.00 to +1.06 pp.
- **Exposure caveat:** among treated customers who were exposed, 41.5% visit, against 3.8% in control. That 37.6 pp gap is selection, not effect. Only the intent-to-treat comparison is valid.

### Power and minimum detectable effect (80% power, two-sided 5%, baseline 3.82%)

| Customers | 50/50 split | 85/15 split |
|---|---|---|
| 100K | 0.34 pp | 0.48 pp |
| 1M | 0.11 pp | 0.15 pp |
| 13.98M (full) | 0.029 pp | 0.040 pp |

### Uplift models

| Learner | Test Qini AUC |
|---|---|
| S-learner (selected on valid) | **6,843** |
| T-learner | 5,229 |
| X-learner | 3,560 |
| Class transformation | −1,727 (failed) |
| Random (reference) | 19 |

Top decile observed lift 6.17 pp against an average of 1.03 pp. Predicted uplift drives the top decile, and the bottom decile is near zero (0.09 pp). The learners are trained on a 1.5M-row stratified sample of the train split. Validation and test (about 2.1M rows each) are scored in pandas.

Top SHAP features for the T-learner's uplift: `f6` (0.33), `f0` (0.23), `f2` (0.16).

### Segments

| Segment | Share | Predicted uplift | Observed visit lift |
|---|---|---|---|
| Persuadable | 50.0% | +1.49 pp | +1.97 pp |
| Sure thing | 4.1% | +0.03 pp | +0.14 pp |
| Lost cause | 38.3% | +0.01 pp | +0.01 pp |
| Do-not-disturb | 7.6% | −0.21 pp | +0.06 pp |

The do-not-disturb segment is consistent with its prediction (−0.21 pp) but too small to confirm: the observed lift is +0.06 pp, 95% CI −0.27 to +0.40 pp.

### ROI and targeting (test split, scaled to 13,979,592 customers)

The cutoff (23%) is the profit-maximising share on the valid split. The test split is used only to report results.

| Policy | Share targeted | Incremental visits | Incremental conversions | Cost | Profit | ROI |
|---|---|---|---|---|---|---|
| Target nobody | 0% | 0 | 0 | $0 | $0 | n/a |
| Target everyone | 100% | 144,609 | 15,244 | $698,980 | −$16,903 | −2.4% |
| Random 30% | 30% | 39,347 | 4,447 | $209,694 | −$12,125 | −5.8% |
| **Top 23% by uplift** | **23%** | **115,746** | **12,528** | **$160,765** | **+$398,243** | **248%** |

Earlier runs chose the cutoff on the test split and reported 19% (+$412k, ROI 311%). That figure was optimistic, so it is not used.

Economics: $0.05 per treated customer, $0.50 per incremental visit, $40 per incremental conversion.

Target-everyone spend that reaches sure things or lost causes: 42.4%.

## Architecture

```
Criteo CSV.gz -> bronze Parquet (Hive external table)
              -> silver Parquet (user_id, bucket, split; partitioned by split)
              -> gold Hive tables (HiveQL: experiment summary, balance check, bucket metrics)
              -> experiment analysis (SMD, SRM, ATE, CUPED, power, exposure)
              -> uplift models (S / T / class-transform / X) -> segments, SHAP
              -> ROI and budget curve (cutoff chosen on valid, reported on test) -> CSV extracts (tableau/extracts/)
              -> MLflow runs (local file store, one per learner)
              -> BigQuery (planned: load + analysis SQL in sql/bigquery/)
              -> Tableau Public (planned, built by hand from the extracts)
```

Spark 3.5.3 (local mode, Hive support, local Derby metastore). HiveQL lives in [sql/hive/](sql/hive/).

## How to run

Needs WSL2 Ubuntu on Windows (native Windows Spark can't write Parquet without `winutils`). Java 17 and a Python 3.12 venv are required. [scripts/wsl_env.sh](scripts/wsl_env.sh) documents the setup used here.

```bash
source scripts/wsl_env.sh
python -m oua.lake      # ingest, silver, DQ checks, gold tables, cache benchmark
python -m oua.ab_test   # randomization, ATE, CUPED, power, exposure
python -m oua.uplift    # uplift models, Qini, deciles, segments, SHAP
python -m oua.roi       # policies, budget curve, sensitivity
python -m oua.export    # Tableau extracts
python -m pytest -q     # 16 tests
```

On this machine the lake step took about 15 minutes, and the full run from lake to export took about an hour. WSL was given 4 GB of memory in `%USERPROFILE%\.wslconfig`.

## Performance note

Caching the silver table made the timing benchmark slower: 5.2 s without the cache, 24.9 s with it. The 3 GB of Spark memory cannot hold the table, so the cache spills to disk. I report the measured numbers rather than tuning the benchmark to look better.

## Tests

16 tests: 13 pure-Python tests for the statistics, uplift evaluation and ROI maths in [tests/test_stats.py](tests/test_stats.py) (one checks the z-test against a hand calculation), and 3 Spark tests for the silver transform (exact duplicates kept, null outcomes dropped, split exact per stratum).

## Remaining work

- **Tableau Public:** needs Tableau Desktop, which the pipeline can't run. Build the three views from [tableau/extracts/](tableau/extracts/). The HTML dashboard at `outputs/dashboard/index.html` covers the same views in the meantime (rebuild with `python scripts/build_dashboard.py`).
- MLflow is done: `python -m oua.uplift` logs one run per learner to `$OUA_DATA_DIR/mlruns` (view with `mlflow ui --backend-store-uri $OUA_DATA_DIR/mlruns`).

## Limitations

See [docs/limitations.md](docs/limitations.md). The main ones: the features are imbalanced beyond chance and the CUPED estimate disagrees with the raw estimate; exact duplicates are kept but unexplained; the economics are assumptions. The cutoff is now chosen on the valid split.
