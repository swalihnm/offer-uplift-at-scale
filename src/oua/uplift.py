"""Uplift models (S, T, class-transformation, X), evaluation, segments and SHAP.

Models are trained on a stratified sample of the train split (treatment x visit).
Model selection uses the valid split. The reported numbers use the test split.
Scoring runs in pandas: LightGBM models are not Spark-native, and the valid and
test splits (about 2.1M rows each) fit in memory.

Run:  python -m oua.uplift
"""

import json

import lightgbm as lgb
import numpy as np
import pandas as pd
import shap
from pyspark.sql import functions as F

from oua.spark import DATA_DIR, ROOT, get_spark

FEATURES = [f"f{i}" for i in range(12)]
METRICS_DIR = ROOT / "outputs" / "metrics"
SCORES_PATH = DATA_DIR / "gold" / "test_scores.parquet"
VALID_SCORES_PATH = DATA_DIR / "gold" / "valid_scores.parquet"
MLFLOW_DIR = DATA_DIR / "mlruns"
TRAIN_SAMPLE_ROWS = 1_500_000
SEED = 42
PARAMS = dict(
    n_estimators=300,
    learning_rate=0.05,
    num_leaves=63,
    min_child_samples=200,
    subsample=0.8,
    subsample_freq=1,
    colsample_bytree=0.9,
    random_state=SEED,
    n_jobs=-1,
    verbose=-1,
)


# ---------- evaluation (pure, unit-tested) ----------


def qini_curve(y: np.ndarray, t: np.ndarray, score: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Cumulative incremental outcome when the top-scored fraction is targeted.

    gain(q) = Y_treated(q) - Y_control(q) * N_treated(q) / N_control(q)
    """
    order = np.argsort(-score, kind="stable")
    y, t = y[order].astype(float), t[order].astype(float)
    n = len(y)
    cum_t = np.cumsum(t)
    cum_c = np.cumsum(1 - t)
    cum_y_t = np.cumsum(y * t)
    cum_y_c = np.cumsum(y * (1 - t))
    scale = np.divide(cum_t, cum_c, out=np.zeros(n), where=cum_c > 0)
    gain = cum_y_t - cum_y_c * scale
    fractions = np.concatenate([[0.0], np.arange(1, n + 1) / n])
    return fractions, np.concatenate([[0.0], gain])


def qini_auc(y: np.ndarray, t: np.ndarray, score: np.ndarray) -> float:
    """Area between the model's Qini curve and the random-targeting line."""
    f, g = qini_curve(y, t, score)
    random_line = g[-1] * f
    return float(np.trapz(g - random_line, f))


def decile_table(y: np.ndarray, t: np.ndarray, score: np.ndarray) -> pd.DataFrame:
    """Observed lift per predicted-uplift decile. Decile 1 is the highest predicted uplift."""
    df = pd.DataFrame({"y": y, "t": t, "score": score})
    df["decile"] = pd.qcut(df["score"].rank(method="first", ascending=False), 10, labels=range(1, 11))
    rows = []
    for d, g in df.groupby("decile", observed=True):
        rate_t = g.loc[g["t"] == 1, "y"].mean()
        rate_c = g.loc[g["t"] == 0, "y"].mean()
        rows.append({"decile": int(d), "n": len(g), "rate_treated": rate_t,
                     "rate_control": rate_c, "observed_lift": rate_t - rate_c})
    return pd.DataFrame(rows)


def assign_segments(tau: np.ndarray, baseline: np.ndarray) -> np.ndarray:
    """Four standard groups. Thresholds are medians on the scored sample.

    do_not_disturb : predicted uplift < 0 (the offer lowers the outcome)
    persuadable    : uplift at or above the median (and not negative)
    sure_thing     : uplift below the median and baseline at or above the median
    lost_cause     : uplift below the median and baseline below the median
    """
    med_tau = np.median(tau)
    med_base = np.median(baseline)
    return np.where(
        tau < 0, "do_not_disturb",
        np.where(
            tau >= med_tau, "persuadable",
            np.where(baseline >= med_base, "sure_thing", "lost_cause"),
        ),
    )


# ---------- uplift learners ----------


def fit_s_learner(X, t, y):
    model = lgb.LGBMClassifier(**PARAMS).fit(np.column_stack([X, t]), y)

    def predict(Xn):
        p1 = model.predict_proba(np.column_stack([Xn, np.ones(len(Xn))]))[:, 1]
        p0 = model.predict_proba(np.column_stack([Xn, np.zeros(len(Xn))]))[:, 1]
        return p1 - p0

    return predict


def fit_t_learner(X, t, y):
    m1 = lgb.LGBMClassifier(**PARAMS).fit(X[t == 1], y[t == 1])
    m0 = lgb.LGBMClassifier(**PARAMS).fit(X[t == 0], y[t == 0])
    return lambda Xn: m1.predict_proba(Xn)[:, 1] - m0.predict_proba(Xn)[:, 1]


def fit_class_transformation(X, t, y, pi: float):
    """Jaskowski & Jaroszewicz. Z = YT/pi + (1-Y)(1-T)/(1-pi), so E[Z|X] = 1 + uplift."""
    z = y * t / pi + (1 - y) * (1 - t) / (1 - pi)
    model = lgb.LGBMRegressor(**PARAMS).fit(X, z)
    return lambda Xn: model.predict(Xn) - 1.0


def fit_x_learner(X, t, y, pi: float):
    """Kunzel et al. (2019). Imputed effects from the T-learner outcome models, then blended."""
    m1 = lgb.LGBMClassifier(**PARAMS).fit(X[t == 1], y[t == 1])
    m0 = lgb.LGBMClassifier(**PARAMS).fit(X[t == 0], y[t == 0])
    d1 = y[t == 1] - m0.predict_proba(X[t == 1])[:, 1]
    d0 = m1.predict_proba(X[t == 0])[:, 1] - y[t == 0]
    tau1 = lgb.LGBMRegressor(**PARAMS).fit(X[t == 1], d1)
    tau0 = lgb.LGBMRegressor(**PARAMS).fit(X[t == 0], d0)

    def predict(Xn):
        return pi * tau0.predict(Xn) + (1 - pi) * tau1.predict(Xn)

    return predict


# ---------- pipeline ----------


def load_sample(spark, split_name: str, n_rows: int) -> pd.DataFrame:
    """Stratified sample (treatment x visit) of one split. Partition pruning on `split`."""
    base = spark.table("oua.silver_criteo").filter(F.col("split") == split_name)
    frac = min(1.0, n_rows / base.count())
    strat = base.withColumn("strat", F.col("treatment") * 2 + F.col("visit"))
    sampled = strat.sampleBy("strat", {k: frac for k in range(4)}, seed=SEED)
    return sampled.select("user_id", *FEATURES, "treatment", "visit", "conversion").toPandas()


def load_split(spark, split_name: str) -> pd.DataFrame:
    return (
        spark.table("oua.silver_criteo")
        .filter(F.col("split") == split_name)
        .select("user_id", *FEATURES, "treatment", "visit", "conversion")
        .toPandas()
    )


def main() -> None:
    spark = get_spark("oua-uplift")
    METRICS_DIR.mkdir(parents=True, exist_ok=True)
    SCORES_PATH.parent.mkdir(parents=True, exist_ok=True)

    train = load_sample(spark, "train", TRAIN_SAMPLE_ROWS)
    valid = load_split(spark, "valid")
    test = load_split(spark, "test")
    print(f"train sample={len(train):,}  valid={len(valid):,}  test={len(test):,}")

    X = train[FEATURES].to_numpy()
    t = train["treatment"].to_numpy()
    y = train["visit"].to_numpy()
    pi = float(t.mean())

    print("== Fitting learners ==")
    learners = {
        "s_learner": fit_s_learner(X, t, y),
        "t_learner": fit_t_learner(X, t, y),
        "class_transformation": fit_class_transformation(X, t, y, pi),
        "x_learner": fit_x_learner(X, t, y, pi),
    }
    baseline_model = lgb.LGBMClassifier(**PARAMS).fit(X[t == 0], y[t == 0])

    def score_frame(df: pd.DataFrame) -> dict:
        Xn = df[FEATURES].to_numpy()
        return {name: fn(Xn) for name, fn in learners.items()}

    print("== Evaluating on valid (model selection) and test (reporting) ==")
    valid_scores = score_frame(valid)
    test_scores = score_frame(test)
    comparison = {}
    for name in learners:
        comparison[name] = {
            "valid_qini_auc": qini_auc(valid["visit"].to_numpy(), valid["treatment"].to_numpy(), valid_scores[name]),
            "test_qini_auc": qini_auc(test["visit"].to_numpy(), test["treatment"].to_numpy(), test_scores[name]),
        }
        print(name, comparison[name])

    # Sign check: learners that are correct should agree in direction on the same customers.
    names = list(learners)
    corr = pd.DataFrame(
        np.corrcoef(np.column_stack([test_scores[n] for n in names]), rowvar=False),
        index=names, columns=names,
    )
    print("correlation of test uplift scores between learners:")
    print(corr.round(3).to_string())

    best = max(learners, key=lambda n: comparison[n]["valid_qini_auc"])
    print(f"Selected on valid: {best}")

    # Valid-split scores for the targeting cutoff (roi.py), so the cutoff never sees the test split.
    valid_out = valid[["user_id", "treatment", "visit", "conversion"]].copy()
    valid_out["tau"] = valid_scores[best]
    valid_out["baseline"] = baseline_model.predict_proba(valid[FEATURES].to_numpy())[:, 1]
    valid_out.to_parquet(VALID_SCORES_PATH, index=False)

    # Random-model reference, so the README can state "vs ~0 for random".
    rng = np.random.default_rng(SEED)
    random_scores = rng.random(len(test))
    random_qini = qini_auc(test["visit"].to_numpy(), test["treatment"].to_numpy(), random_scores)

    tau = test_scores[best]
    baseline = baseline_model.predict_proba(test[FEATURES].to_numpy())[:, 1]
    segments = assign_segments(tau, baseline)

    deciles = decile_table(test["visit"].to_numpy(), test["treatment"].to_numpy(), tau)
    deciles.to_csv(METRICS_DIR / "uplift_deciles.csv", index=False)
    print(deciles.to_string(index=False))

    seg_profile = (
        pd.DataFrame({"segment": segments, "treatment": test["treatment"], "visit": test["visit"],
                      "conversion": test["conversion"], "tau": tau, "baseline": baseline})
        .groupby("segment")
        .apply(lambda g: pd.Series({
            "share": len(g) / len(test),
            "mean_predicted_uplift": g["tau"].mean(),
            "baseline_visit_rate": g.loc[g["treatment"] == 0, "visit"].mean(),
            "observed_visit_lift": g.loc[g["treatment"] == 1, "visit"].mean()
                                   - g.loc[g["treatment"] == 0, "visit"].mean(),
        }), include_groups=False)
        .reset_index()
    )
    seg_profile.to_csv(METRICS_DIR / "segment_profile.csv", index=False)
    print(seg_profile.to_string(index=False))

    print("== SHAP on the T-learner uplift (tau = m1(x) - m0(x)) ==")
    sample_idx = np.random.default_rng(SEED).choice(len(test), size=5000, replace=False)
    Xs = test[FEATURES].to_numpy()[sample_idx]
    m1 = lgb.LGBMClassifier(**PARAMS).fit(X[t == 1], y[t == 1])
    m0 = lgb.LGBMClassifier(**PARAMS).fit(X[t == 0], y[t == 0])
    shap1 = shap.TreeExplainer(m1).shap_values(Xs)
    shap0 = shap.TreeExplainer(m0).shap_values(Xs)
    shap1 = shap1[1] if isinstance(shap1, list) else shap1
    shap0 = shap0[1] if isinstance(shap0, list) else shap0
    importance = pd.DataFrame({
        "feature": FEATURES,
        "mean_abs_shap_uplift": np.abs(shap1 - shap0).mean(axis=0),
    }).sort_values("mean_abs_shap_uplift", ascending=False)
    importance.to_csv(METRICS_DIR / "shap_importance.csv", index=False)
    print(importance.to_string(index=False))

    scores_out = test[["user_id", "treatment", "visit", "conversion"]].copy()
    scores_out["tau"] = tau
    scores_out["baseline"] = baseline
    scores_out["segment"] = segments
    scores_out.to_parquet(SCORES_PATH, index=False)

    overall_lift = float(test.loc[test["treatment"] == 1, "visit"].mean() - test.loc[test["treatment"] == 0, "visit"].mean())
    top = deciles.iloc[0]["observed_lift"]
    bottom = deciles.iloc[-1]["observed_lift"]
    results = {
        "selected_model": best,
        "comparison": comparison,
        "random_test_qini_auc": random_qini,
        "test_qini_auc_selected": comparison[best]["test_qini_auc"],
        "overall_observed_lift_test": overall_lift,
        "top_decile_lift": top,
        "bottom_decile_lift": bottom,
        "top_decile_vs_average_lift_x": top / overall_lift,
        "pi_treated_train": pi,
        "segment_shares": seg_profile.set_index("segment")["share"].to_dict(),
    }
    (METRICS_DIR / "uplift.json").write_text(json.dumps(results, indent=2, default=float), encoding="utf-8")
    print(json.dumps(results, indent=2, default=float))
    log_to_mlflow(comparison, best, pi, len(train), deciles, [METRICS_DIR / "uplift.json",
                  METRICS_DIR / "uplift_deciles.csv", METRICS_DIR / "segment_profile.csv",
                  METRICS_DIR / "shap_importance.csv"])
    spark.stop()


def log_to_mlflow(comparison: dict, selected: str, pi: float, train_rows: int,
                  deciles: pd.DataFrame, artifacts: list) -> None:
    """One MLflow run per learner (local file store on the Linux filesystem), plus the selected run's artifacts."""
    import mlflow

    MLFLOW_DIR.mkdir(parents=True, exist_ok=True)
    mlflow.set_tracking_uri(MLFLOW_DIR.as_uri())
    mlflow.set_experiment("offer-uplift")
    for name, metrics in comparison.items():
        with mlflow.start_run(run_name=name):
            mlflow.log_params({"learner": name, "train_rows": train_rows, "train_treated_share": round(pi, 6),
                               "selected_on_valid": name == selected, **PARAMS})
            mlflow.log_metrics(metrics)
            if name == selected:
                mlflow.log_metric("top_decile_lift", float(deciles.iloc[0]["observed_lift"]))
                mlflow.log_metric("bottom_decile_lift", float(deciles.iloc[-1]["observed_lift"]))
                for path in artifacts:
                    mlflow.log_artifact(str(path))


if __name__ == "__main__":
    main()
