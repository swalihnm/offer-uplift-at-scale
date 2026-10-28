# Progress log

Every number below comes from a script output or a command output, not from memory.

## Step 0: environment (partial)

- Downloaded `criteo-research-uplift-v2.1.csv.gz` from the GitHub mirror (jszymon/uplift_sklearn_data). 311,422,618 bytes.
- SHA-256 matches the published value (`2716e1bf…f616dc`).
- Source line count: `zcat | wc -l` = 13,979,593 including the header, so **13,979,592 data rows**.
- Header: `f0..f11, treatment, conversion, visit, exposure`.
- PySpark 3.5.3 installed in `.venv` (Windows Python 3.12). Java on the machine is 18.0.1.1, not 17.
- Spark starts and counts on Windows (`range(1000).count()` = 1000).
- **Blocked:** any Spark write fails with `HADOOP_HOME and hadoop.home.dir are unset` (no `winutils.exe`). The spec asks for WSL2 Ubuntu with Java 17 for this reason. WSL has no Ubuntu distro yet, and installing one needs an elevated terminal.

## Full run in WSL (final)

Run in WSL Ubuntu, Java 17, Python 3.12, PySpark 3.5.3. Each step's log is in `~/tools/*.log` in WSL. The numbers below come from the final run.

- **Tests:** 16 passed (`pytest -q`).
- **Lake:** source rows 13,979,592 = bronze rows; 0 null outcomes; treated share 0.85; 1,259,545 exact-duplicate rows kept as separate users; silver 13,979,592 with unique `user_id`; split train 9,785,716 / valid 2,096,940 / test 2,096,936. Gold experiment summary: treated n 11,882,655 (visit 4.854%), control n 2,096,937 (visit 3.820%).
- **Caching benchmark:** 5.18 s without cache, 24.9 s with cache (cache spills to disk on the 3 GB Spark heap).
- **Randomization:** max |SMD| 0.0488 (f3), 0 of 12 features ≥ 0.1; SRM chi² 1.8e-6, p = 0.9989.
- **ATE visit:** +1.034 pp, 95% CI [1.006, 1.063] pp, rel +27.1%, z 65.2. Bucket-bootstrap CI [1.004, 1.062] pp.
- **ATE conversion:** +0.115 pp, 95% CI [0.108, 0.122] pp, rel +59.4%.
- **CUPED (visit):** variance reduction 28.0%; adjusted lift +0.699 pp, CI [0.674, 0.723] pp. Disagrees with the raw estimate; unresolved (see `docs/limitations.md`).
- **Uplift test Qini AUC:** S 6,843; T 5,229; X 3,560; class-transform −1,727; random 19. S-learner selected on valid.
- **Top decile lift** 6.17 pp vs average 1.03 pp (5.96×).
- **ROI** (test split scaled to 13,979,592): target everyone profit −$16,903; top 19% profit +$412,475, ROI 311%; profit-max share 19%; top 20% keeps 80.0% of incremental conversions at 20.0% of cost; wasted (sure thing + lost cause) share of target-everyone cost 42.4%.
- **Sensitivity:** optimal share 10%–36.5%, 6 distinct values; target-everyone unprofitable in 5 of 9 cells.

Bugs fixed during this run, before the final numbers:
1. Exact-duplicate removal broke randomization (treated share 83.9%, SRM p = 0). Fixed by keeping duplicates.
2. Spark `sample()` followed by `limit()` returned all-zero outcomes, so CUPED showed 0% reduction. Fixed by sampling then trimming in pandas.
3. `bucket` stored as INT64 against an INT DDL. Fixed with a cast.
4. Spark driver ran out of memory at 2 GB. WSL memory raised to 4 GB; driver set to 3 GB.
5. PySpark's pandas conversion needed `distutils`, missing on Python 3.12. Fixed by installing setuptools.

## Code written, not yet run end-to-end

- Steps A–E modules written: `ingest.py`, `lake.py`, `sql/hive/*.hql`, `ab_test.py`, `uplift.py`, `roi.py`, `export.py`, `bq_load.py`, `sql/bigquery/*.sql`.
- Pure-Python tests (`tests/test_stats.py`): **13 passed** on Windows (`pytest -q tests/test_stats.py`).
- Spark tests (`tests/test_silver.py`): **3 failed** on Windows. The Spark Python worker socket times out (`SocketTimeoutException: Accept timed out` in `PythonWorkerFactory`). This is a Windows worker-launch problem, not a verified logic bug. They need to run in WSL to confirm.
- WSL check at this point: no Ubuntu distro is installed (`wsl -d Ubuntu` → WSL_E_DISTRO_NOT_FOUND).
- Deviations from the spec so far:
  - Uplift models are scored in pandas, not Spark. LightGBM is not Spark-native, and the valid and test splits fit in memory.
  - MLflow logging is not included yet. It isn't in `requirements.txt`.
  - The spec's "~13.9M rows" is correct (13,979,592). A web search suggested 25.3M for v2.1, but the file itself says 13.98M.
