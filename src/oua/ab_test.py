"""Experiment analysis: randomization checks, ATE, CUPED, power/MDE, exposure caveat.

Run:  python -m oua.ab_test
"""

import json
import math

import numpy as np
import pandas as pd
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from scipy import stats

from oua.spark import ROOT, get_spark

FEATURES = [f"f{i}" for i in range(12)]
METRICS_DIR = ROOT / "outputs" / "metrics"
Z_975 = stats.norm.ppf(0.975)
COVARIATE_SAMPLE_ROWS = 2_000_000
SEED = 42


# ---------- pure functions (unit-tested) ----------


def two_prop_test(x1: float, n1: float, x0: float, n0: float) -> dict:
    """Two-proportion z-test. The z-test uses the pooled SE; the CI uses the unpooled SE."""
    p1, p0 = x1 / n1, x0 / n0
    diff = p1 - p0
    p_pool = (x1 + x0) / (n1 + n0)
    se_pool = math.sqrt(p_pool * (1 - p_pool) * (1 / n1 + 1 / n0))
    z = diff / se_pool
    se_unpooled = math.sqrt(p1 * (1 - p1) / n1 + p0 * (1 - p0) / n0)
    return {
        "p_treated": p1,
        "p_control": p0,
        "abs_lift": diff,
        "rel_lift": diff / p0,
        "z": z,
        "p_value": 2 * stats.norm.sf(abs(z)),
        "ci_low": diff - Z_975 * se_unpooled,
        "ci_high": diff + Z_975 * se_unpooled,
    }


def smd(mean1: float, sd1: float, mean0: float, sd0: float) -> float:
    """Standardized mean difference with the pooled SD."""
    return (mean1 - mean0) / math.sqrt((sd1**2 + sd0**2) / 2)


def srm_test(n_treated: int, n_control: int, expected_treated_share: float = 0.85) -> dict:
    """Sample-ratio-mismatch chi-square test against the designed split."""
    total = n_treated + n_control
    observed = [n_treated, n_control]
    expected = [total * expected_treated_share, total * (1 - expected_treated_share)]
    chi2, p = stats.chisquare(observed, f_exp=expected)
    return {"chi2": chi2, "p_value": p, "observed_treated_share": n_treated / total}


def power_mde(n_total: int, baseline: float, treated_share: float,
              alpha: float = 0.05, power: float = 0.80) -> dict:
    """Minimum detectable absolute and relative lift for a two-proportion test."""
    n1 = n_total * treated_share
    n0 = n_total * (1 - treated_share)
    z_alpha = stats.norm.ppf(1 - alpha / 2)
    z_beta = stats.norm.ppf(power)
    se = math.sqrt(baseline * (1 - baseline) * (1 / n1 + 1 / n0))
    mde_abs = (z_alpha + z_beta) * se
    return {"mde_abs": mde_abs, "mde_rel": mde_abs / baseline}


def cuped_theta(X: np.ndarray, y: np.ndarray) -> tuple[float, np.ndarray]:
    """OLS of the outcome on the covariates (with intercept). Returns (intercept, betas)."""
    design = np.column_stack([np.ones(len(X)), X])
    coef, *_ = np.linalg.lstsq(design, y, rcond=None)
    return float(coef[0]), coef[1:]


# ---------- Spark steps ----------


def balance_table(spark: SparkSession) -> pd.DataFrame:
    """SMD for each feature, treated vs control, from the gold balance table."""
    bal = spark.table("oua.gold_balance_check").toPandas()
    t = bal[bal["treatment"] == 1].set_index("feature")
    c = bal[bal["treatment"] == 0].set_index("feature")
    out = pd.DataFrame({
        "feature": t.index,
        "mean_treated": t["mean_val"].values,
        "mean_control": c.loc[t.index, "mean_val"].values,
    })
    out["smd"] = [
        smd(t.loc[f, "mean_val"], t.loc[f, "sd_val"], c.loc[f, "mean_val"], c.loc[f, "sd_val"])
        for f in t.index
    ]
    return out


def naive_effect(silver: DataFrame, outcome: str) -> dict:
    """Difference in means with a Welch CI, on the raw outcome."""
    stats_df = silver.groupBy("treatment").agg(
        F.count(F.lit(1)).alias("n"),
        F.avg(outcome).alias("mean"),
        F.var_samp(outcome).alias("var"),
    ).collect()
    by = {r["treatment"]: r for r in stats_df}
    t, c = by[1], by[0]
    diff = t["mean"] - c["mean"]
    se = math.sqrt(t["var"] / t["n"] + c["var"] / c["n"])
    return {
        "mean_treated": t["mean"],
        "mean_control": c["mean"],
        "abs_lift": diff,
        "ci_low": diff - Z_975 * se,
        "ci_high": diff + Z_975 * se,
        "outcome_variance": (t["var"] * t["n"] + c["var"] * c["n"]) / (t["n"] + c["n"]),
    }


def fit_covariate_model(silver: DataFrame, outcome: str) -> tuple[float, np.ndarray]:
    """Fit outcome ~ features on a random sample (pooled, ignores treatment).

    The sample is drawn with sample() and trimmed in pandas. Using limit() after sample()
    instead took rows from one partition and returned all-zero outcomes.
    """
    fraction = min(1.0, COVARIATE_SAMPLE_ROWS / silver.count() * 1.2)
    sample = silver.select(*FEATURES, outcome).sample(withReplacement=False, fraction=fraction, seed=SEED).toPandas()
    if len(sample) > COVARIATE_SAMPLE_ROWS:
        sample = sample.sample(n=COVARIATE_SAMPLE_ROWS, random_state=SEED)
    if sample[outcome].var() == 0:
        raise ValueError("covariate sample has no variation in the outcome")
    return cuped_theta(sample[FEATURES].to_numpy(), sample[outcome].to_numpy())


def cuped_effect(silver: DataFrame, outcome: str, intercept: float, betas: np.ndarray) -> dict:
    """Regression-adjusted (CUPED) effect. The adjustment uses only pre-treatment features."""
    pred = F.lit(intercept)
    for b, f in zip(betas, FEATURES):
        pred = pred + F.lit(float(b)) * F.col(f)
    with_pred = silver.withColumn("_pred", pred)
    mu_pred = with_pred.agg(F.avg("_pred")).collect()[0][0]
    adjusted = with_pred.withColumn(
        "y_adj", F.col(outcome) - (F.col("_pred") - F.lit(mu_pred))
    )
    effect = naive_effect(adjusted, "y_adj")
    effect["outcome_variance_adjusted"] = effect.pop("outcome_variance")
    return effect


def exposure_caveat(silver: DataFrame) -> dict:
    """Intent-to-treat vs an exposed-only comparison. The exposed-only one is biased."""
    itt = silver.groupBy("treatment").agg(F.avg("visit").alias("visit_rate")).collect()
    itt_by = {r["treatment"]: r["visit_rate"] for r in itt}
    exposed = silver.filter((F.col("treatment") == 1) & (F.col("exposure") == 1))
    exposed_rate = exposed.agg(F.avg("visit")).collect()[0][0]
    unexposed_treated = silver.filter((F.col("treatment") == 1) & (F.col("exposure") == 0))
    unexposed_rate = unexposed_treated.agg(F.avg("visit")).collect()[0][0]
    return {
        "itt_treated_visit_rate": itt_by[1],
        "control_visit_rate": itt_by[0],
        "exposed_visit_rate": exposed_rate,
        "unexposed_treated_visit_rate": unexposed_rate,
        "exposed_minus_control": exposed_rate - itt_by[0],
    }


def bucket_bootstrap_ci(spark: SparkSession, outcome: str, n_boot: int = 2000, seed: int = 7) -> dict:
    """Bootstrap the ATE by resampling the 100 hash buckets (a cluster-style check on the CI)."""
    b = spark.table("oua.gold_bucket_metrics").toPandas()
    pivot = b.pivot_table(index="bucket", columns="treatment", values=["n", "visits", "conversions"], aggfunc="sum")
    key = {"visit": "visits", "conversion": "conversions"}[outcome]
    rate_t = pivot[(key, 1)].to_numpy() / pivot[("n", 1)].to_numpy()
    rate_c = pivot[(key, 0)].to_numpy() / pivot[("n", 0)].to_numpy()
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(rate_t), size=(n_boot, len(rate_t)))
    boot = rate_t[idx].mean(axis=1) - rate_c[idx].mean(axis=1)
    return {"ci_low": float(np.percentile(boot, 2.5)), "ci_high": float(np.percentile(boot, 97.5))}


def main() -> None:
    spark = get_spark("oua-ab")
    METRICS_DIR.mkdir(parents=True, exist_ok=True)
    silver = spark.table("oua.silver_criteo")
    results: dict = {}

    print("== Randomization: balance (SMD) ==")
    bal = balance_table(spark)
    bal.to_csv(METRICS_DIR / "balance_smd.csv", index=False)
    results["max_abs_smd"] = float(bal["smd"].abs().max())
    results["features_with_abs_smd_ge_0.1"] = int((bal["smd"].abs() >= 0.1).sum())
    print(bal.to_string(index=False))

    print("== Randomization: sample ratio mismatch ==")
    summary = spark.table("oua.gold_experiment_summary").toPandas().set_index("treatment")
    results["srm"] = srm_test(int(summary.loc[1, "n"]), int(summary.loc[0, "n"]))
    print(json.dumps(results["srm"], indent=2))

    print("== ATE (intent-to-treat), two-proportion z-test ==")
    results["ate"] = {}
    for outcome, x_col in [("visit", "visits"), ("conversion", "conversions")]:
        x1, n1 = summary.loc[1, x_col], summary.loc[1, "n"]
        x0, n0 = summary.loc[0, x_col], summary.loc[0, "n"]
        results["ate"][outcome] = two_prop_test(x1, n1, x0, n0)
        results["ate"][outcome]["bucket_bootstrap_ci"] = bucket_bootstrap_ci(spark, outcome)
    print(json.dumps(results["ate"], indent=2))

    print("== CUPED (regression adjustment) on visit ==")
    intercept, betas = fit_covariate_model(silver, "visit")
    raw = naive_effect(silver, "visit")
    adj = cuped_effect(silver, "visit", intercept, betas)
    results["cuped_visit"] = {
        "raw_outcome_variance": raw["outcome_variance"],
        "adjusted_outcome_variance": adj["outcome_variance_adjusted"],
        "variance_reduction": 1 - adj["outcome_variance_adjusted"] / raw["outcome_variance"],
        "raw_ci": [raw["ci_low"], raw["ci_high"]],
        "adjusted_ci": [adj["ci_low"], adj["ci_high"]],
        "raw_abs_lift": raw["abs_lift"],
        "adjusted_abs_lift": adj["abs_lift"],
    }
    print(json.dumps(results["cuped_visit"], indent=2))

    print("== Power / MDE ==")
    baseline = float(summary.loc[0, "visit_rate"])
    rows = []
    for n in [100_000, 1_000_000, 13_979_592]:
        for share in [0.50, 0.85]:
            m = power_mde(n, baseline, share)
            rows.append({"n_total": n, "treated_share": share, "baseline_visit_rate": baseline, **m})
    power = pd.DataFrame(rows)
    power.to_csv(METRICS_DIR / "power_table.csv", index=False)
    print(power.to_string(index=False))
    results["power_table"] = rows

    print("== Exposure caveat ==")
    results["exposure"] = exposure_caveat(silver)
    print(json.dumps(results["exposure"], indent=2))

    (METRICS_DIR / "ab_test.json").write_text(json.dumps(results, indent=2, default=float), encoding="utf-8")
    spark.stop()


if __name__ == "__main__":
    main()
