"""Pure-Python tests for the experiment, uplift and ROI maths. No Spark needed."""

import numpy as np
import pandas as pd
import pytest

from oua.ab_test import cuped_theta, power_mde, smd, srm_test, two_prop_test
from oua.roi import budget_curve, economics, policy_outcome
from oua.uplift import assign_segments, qini_auc, qini_curve


# ---------- experiment analysis ----------


def test_two_prop_test_matches_hand_computed_example():
    # p1 = 0.06, p0 = 0.05, n = 1000 each. Pooled p = 0.055.
    # SE_pool = sqrt(0.055 * 0.945 * 0.002) = 0.0101956, so z = 0.01 / SE = 0.98077.
    # Two-sided p = 2 * (1 - Phi(0.98077)) = 0.3268.
    res = two_prop_test(60, 1000, 50, 1000)
    assert res["abs_lift"] == pytest.approx(0.01)
    assert res["rel_lift"] == pytest.approx(0.2)
    assert res["z"] == pytest.approx(0.98077, abs=1e-4)
    assert res["p_value"] == pytest.approx(0.3268, abs=1e-3)
    assert res["ci_low"] < 0.01 < res["ci_high"]


def test_smd_is_zero_for_identical_groups_and_signed():
    assert smd(0.5, 1.0, 0.5, 1.0) == 0
    assert smd(1.0, 1.0, 0.0, 1.0) == pytest.approx(1.0)


def test_srm_test_passes_on_designed_split_and_fails_on_skew():
    ok = srm_test(int(0.85 * 100_000), int(0.15 * 100_000))
    assert ok["p_value"] > 0.5
    bad = srm_test(60_000, 40_000)
    assert bad["p_value"] < 1e-6


def test_power_mde_shrinks_with_sample_size():
    small = power_mde(100_000, 0.03, 0.5)["mde_abs"]
    large = power_mde(1_000_000, 0.03, 0.5)["mde_abs"]
    assert large < small
    assert large == pytest.approx(small / np.sqrt(10), rel=1e-6)


def test_cuped_never_increases_variance():
    rng = np.random.default_rng(0)
    X = rng.normal(size=(20_000, 5))
    y = X @ np.array([1.0, -0.5, 0.2, 0.0, 0.3]) + rng.normal(size=20_000)
    intercept, betas = cuped_theta(X, y)
    adjusted = y - (X @ betas + intercept - np.mean(X @ betas + intercept))
    assert adjusted.var() <= y.var()
    assert 1 - adjusted.var() / y.var() > 0.5  # this signal is strong, so the reduction is large


# ---------- uplift evaluation ----------


def test_random_model_has_qini_near_zero():
    rng = np.random.default_rng(1)
    n = 200_000
    t = rng.integers(0, 2, n)
    y = (rng.random(n) < np.where(t == 1, 0.06, 0.05)).astype(int)
    score = rng.random(n)
    assert abs(qini_auc(y, t, score)) < 0.02 * n * 0.01


def test_perfect_model_beats_random_on_toy_data():
    # Customers 0..499 respond only if treated. Customers 500..999 never respond.
    n = 1000
    t = np.tile([0, 1], n // 2)
    persuadable = np.arange(n) < 500
    y = (persuadable & (t == 1)).astype(int)
    perfect_score = persuadable.astype(float)  # the true uplift is 1 for persuadables, 0 otherwise
    rng = np.random.default_rng(2)
    assert qini_auc(y, t, perfect_score) > qini_auc(y, t, rng.random(n)) + 50


def test_qini_curve_starts_at_zero_and_ends_at_total_gain():
    y = np.array([1, 0, 1, 0])
    t = np.array([1, 1, 0, 0])
    f, g = qini_curve(y, t, np.array([0.9, 0.5, 0.2, 0.1]))
    assert f[0] == 0 and g[0] == 0
    assert f[-1] == pytest.approx(1.0)


def test_segments_cover_each_customer_once_and_respect_negative_uplift():
    tau = np.array([-0.1, 0.5, 0.4, 0.05, 0.01, 0.02])
    baseline = np.array([0.1, 0.1, 0.9, 0.9, 0.1, 0.9])
    seg = assign_segments(tau, baseline)
    assert seg[0] == "do_not_disturb"
    assert seg[1] == "persuadable"
    assert set(seg) <= {"persuadable", "sure_thing", "lost_cause", "do_not_disturb"}
    assert len(seg) == len(tau)


# ---------- ROI ----------


def _toy_scored(n: int = 10_000, seed: int = 3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    t = (rng.random(n) < 0.85).astype(int)
    visit = (rng.random(n) < np.where(t == 1, 0.06, 0.05)).astype(int)
    conv = (visit & (rng.random(n) < 0.1)).astype(int)
    tau = rng.normal(size=n)
    return pd.DataFrame({"treatment": t, "visit": visit, "conversion": conv, "tau": tau})


def test_target_nobody_has_zero_cost_and_zero_value():
    df = _toy_scored()
    out = policy_outcome(df, np.zeros(len(df), dtype=bool), 1_000_000, 0.05, 0.5, 40.0)
    assert out["cost"] == 0
    assert out["incremental_value"] == 0
    assert np.isnan(out["roi"])


def test_target_everyone_matches_ate_times_population():
    df = _toy_scored()
    N = 13_979_592
    out = policy_outcome(df, np.ones(len(df), dtype=bool), N, 0.05, 0.5, 40.0)
    ate = df.loc[df.treatment == 1, "visit"].mean() - df.loc[df.treatment == 0, "visit"].mean()
    assert out["incremental_visits"] == pytest.approx(N * ate)
    assert out["cost"] == pytest.approx(N * 0.05)


def test_budget_curve_fast_path_matches_direct_policy_outcome():
    df = _toy_scored()
    curve = budget_curve(df, 1_000_000, 0.05, 0.5, 40.0, step=0.1)
    ordered = df.sort_values("tau", ascending=False).reset_index(drop=True)
    row = curve.iloc[4]  # 50% targeted
    k = int(round(row["share_targeted"] * len(ordered)))
    mask = np.zeros(len(ordered), dtype=bool)
    mask[:k] = True
    direct = policy_outcome(ordered, mask, 1_000_000, 0.05, 0.5, 40.0)
    assert row["incremental_visits"] == pytest.approx(direct["incremental_visits"])
    assert row["profit"] == pytest.approx(direct["profit"])


def test_economics_profit_is_value_minus_cost():
    out = economics(0.5, 0.01, 0.001, 1_000_000, 0.05, 0.5, 40.0)
    assert out["profit"] == pytest.approx(out["incremental_value"] - out["cost"])
