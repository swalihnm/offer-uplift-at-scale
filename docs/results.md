# Results

Every number here comes from a file in `outputs/metrics/` or `outputs/bigquery/`. Figures are the final run (see `progress.md`). Read [limitations.md](limitations.md) alongside these, especially items 1 and 2.

## Data and randomization

| Item | Value | Source |
|---|---|---|
| Source rows | 13,979,592 | `dq.json` |
| Null outcomes | 0 | `dq.json` |
| Treated share | 85.00% | `dq.json`, `ab_test.json` |
| Exact duplicate rows (kept) | 1,259,545 | `dq.json` |
| Split (train / valid / test) | 9,785,716 / 2,096,940 / 2,096,936 | `dq.json` |
| Sample ratio mismatch | chi² 1.8e-6, p = 0.999 | `ab_test.json` |
| Largest \|SMD\| | 0.049 (f3); 0 of 12 at or above 0.1 | `balance_smd.csv` |

Balance passes the spec's threshold, but at this sample size a clean randomization would give SMDs near 0.001. See limitations item 1.

## Treatment effect (intent-to-treat)

| Outcome | Control | Treated | Lift | 95% CI | Relative |
|---|---|---|---|---|---|
| Visit | 3.82% | 4.85% | +1.03 pp | +1.01 to +1.06 pp | +27% |
| Conversion | 0.194% | 0.309% | +0.12 pp | +0.11 to +0.12 pp | +59% |

Bucket bootstrap (100 buckets, 2,000 resamples) gives a visit CI of +1.00 to +1.06 pp, close to the analytic CI.

**Robustness check on duplicate rows (not in the pipeline):** the 2.2M duplicate rows contain 42 visits, against a 5.9% visit rate for unique treated rows. Restricting to unique rows gives a visit lift of +1.91 pp (treated 5.91% vs control 4.00%). But unique rows are not balanced across arms (83% treated), so this estimate is not clean either. The headline stays at +1.03 pp until the duplicates are explained.

## CUPED

| | Value |
|---|---|
| Outcome variance, raw | 0.04477 |
| Outcome variance, adjusted | 0.03223 |
| Variance reduction | 28.0% |
| Adjusted visit lift | +0.70 pp (CI +0.67 to +0.72 pp) |

The adjusted lift does not agree with the raw lift, and the intervals do not overlap. The gap is exactly the covariate imbalance term: raw minus adjusted equals β·(x̄_treated − x̄_control) = 0.3356 pp, matching the observed gap to eight significant digits. CUPED is calculating correctly. The disagreement is the feature imbalance itself (limitations item 1).

## Power and minimum detectable effect

Baseline visit rate 3.82%, two-sided 5%, 80% power.

| Customers | 50/50 split | 85/15 split |
|---|---|---|
| 100,000 | +0.34 pp | +0.48 pp |
| 1,000,000 | +0.11 pp | +0.15 pp |
| 13,979,592 | +0.03 pp | +0.04 pp |

## Exposure caveat

Among treated customers who were exposed, 41.5% visit, against 3.8% in control. The 37.6 pp gap is selection, so only the intent-to-treat comparison is used.

## Uplift models

| Learner | Valid Qini AUC | Test Qini AUC |
|---|---|---|
| S-learner (selected on valid) | 6,335 | 6,843 |
| T-learner | 4,924 | 5,229 |
| X-learner | 2,750 | 3,560 |
| Class transformation | −1,659 | −1,727 (failed) |
| Random (reference) | — | 19 |

- Top decile observed lift: +6.17 pp. Average test lift: +1.03 pp. Ratio: 6.0×.
- Bottom decile: +0.09 pp.
- Score correlations on test: S with T 0.75, S with X 0.77, T with X 0.85. Class transformation with S −0.11, with T 0.01.
- SHAP (mean |value|, T-learner uplift): f6 0.33, f0 0.23, f2 0.16, f8 0.09, f9 0.05.

The class-transformation learner is reported as failed. On synthetic data with a similar effect it is weakly positive (Qini 34 against 376 for the S-learner), and it stays weak at a 50/50 split (26 against 215). The strongly negative real-data value is not reproduced, so its cause is still open. The likely culprit is the large class weights.

## Segments (test split)

| Segment | Share | Predicted uplift | Observed visit lift |
|---|---|---|---|
| Persuadable | 50.0% | +1.49 pp | +1.97 pp |
| Sure thing | 4.1% | +0.03 pp | +0.14 pp |
| Lost cause | 38.3% | +0.01 pp | +0.01 pp |
| Do-not-disturb | 7.6% | −0.21 pp | +0.06 pp |

The do-not-disturb segment is consistent with its prediction but too small to confirm. Predicted uplift is −0.21 pp, and the observed lift is +0.06 pp with a 95% CI of −0.27 to +0.40 pp, which contains the prediction.

## ROI and targeting

Economics (placeholders, see `conf/economics.yaml`): $0.05 per treated customer, $0.50 per incremental visit, $40 per incremental conversion.

The cutoff is 23%, chosen as the profit-maximising share on the valid split. Results are on the test split, scaled to 13,979,592 customers.

| Policy | Share | Incremental visits | Incremental conversions | Cost | Profit | ROI |
|---|---|---|---|---|---|---|
| Target nobody | 0% | 0 | 0 | $0 | $0 | n/a |
| Target everyone | 100% | 144,609 | 15,244 | $698,980 | −$16,903 | −2.4% |
| Random 30% | 30% | 39,347 | 4,447 | $209,694 | −$12,125 | −5.8% |
| **Top 23% by uplift** | **23%** | **115,746** | **12,528** | **$160,765** | **+$398,243** | **248%** |

- Top 20% by uplift keeps 80% of incremental conversions at 20% of the cost.
- Sure things and lost causes make up 42.4% of target-everyone spend.
- Sensitivity: the valid-chosen cutoff ranges from 11.5% to 31%. Test profit is positive at that cutoff in all 9 cost × value settings. Target everyone is unprofitable in 5 of 9.

## BigQuery (`offer_uplift`, project `gemini-api-key-477720`)

- Top 10% by predicted uplift keeps 81% of incremental visits; top 20% keeps 92%.
- Policy ranking by profit: top 23% first (+$398,244), target everyone last (−$16,903).
- Sure things, lost causes and do-not-disturb together make up 50% of the population.

Sandbox tables expire after 60 days.
