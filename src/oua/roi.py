"""Targeting policies, ROI, budget curve and sensitivity to the economics.

The targeting cutoff is chosen on the valid split and reported on the test split, so the
reported profit is not tuned on the data it is measured on.
Outputs are scaled to the full source population, using the test-split rates.

Run:  python -m oua.roi
"""

import json

import numpy as np
import pandas as pd
import yaml

from oua.spark import DATA_DIR, ROOT
from oua.uplift import SCORES_PATH, VALID_SCORES_PATH

METRICS_DIR = ROOT / "outputs" / "metrics"
ECON_PATH = ROOT / "conf" / "economics.yaml"
DQ_PATH = METRICS_DIR / "dq.json"
RANDOM_SHARE = 0.30
RANDOM_SEED = 42
GRID_STEP = 0.005  # budget-curve resolution: 0.5% of customers


# ---------- pure functions (unit-tested) ----------


def economics(share: float, lift_visit: float, lift_conversion: float, n_population: int,
              cost: float, value_visit: float, value_conversion: float) -> dict:
    """Scale one targeting share to the population and price it."""
    n_target = n_population * share
    incr_visits = n_target * lift_visit
    incr_conversions = n_target * lift_conversion
    cost_total = n_target * cost
    incr_value = incr_visits * value_visit + incr_conversions * value_conversion
    return {
        "share_targeted": share,
        "customers_targeted": n_target,
        "incremental_visits": incr_visits,
        "incremental_conversions": incr_conversions,
        "cost": cost_total,
        "incremental_value": incr_value,
        "profit": incr_value - cost_total,
        "roi": (incr_value - cost_total) / cost_total if cost_total > 0 else float("nan"),
        "cost_per_incremental_conversion": cost_total / incr_conversions if incr_conversions > 0 else float("nan"),
    }


def _lift(treated: pd.DataFrame, control: pd.DataFrame, col: str) -> float:
    if len(treated) == 0 or len(control) == 0:
        return 0.0
    return float(treated[col].mean() - control[col].mean())


def policy_outcome(df: pd.DataFrame, targeted: np.ndarray, n_population: int,
                   cost: float, value_visit: float, value_conversion: float) -> dict:
    """Economics for targeting the rows where `targeted` is True. The lift is the randomized comparison inside that set."""
    sub = df[targeted]
    treated = sub[sub["treatment"] == 1]
    control = sub[sub["treatment"] == 0]
    return economics(
        share=float(targeted.mean()),
        lift_visit=_lift(treated, control, "visit"),
        lift_conversion=_lift(treated, control, "conversion"),
        n_population=n_population,
        cost=cost,
        value_visit=value_visit,
        value_conversion=value_conversion,
    )


def budget_curve(df: pd.DataFrame, n_population: int, cost: float,
                 value_visit: float, value_conversion: float, step: float = GRID_STEP) -> pd.DataFrame:
    """Profit at each share targeted (top-k by predicted uplift), on a fixed grid.

    Uses cumulative sums over the uplift-sorted rows, so each grid point is O(1).
    """
    ordered = df.sort_values("tau", ascending=False).reset_index(drop=True)
    n = len(ordered)
    is_t = ordered["treatment"].to_numpy() == 1
    is_c = ~is_t
    cum_nt, cum_nc = np.cumsum(is_t), np.cumsum(is_c)

    def cum_lift(col: str) -> np.ndarray:
        y = ordered[col].to_numpy(dtype=float)
        cum_yt, cum_yc = np.cumsum(y * is_t), np.cumsum(y * is_c)
        lift = np.zeros(n)
        valid = (cum_nt > 0) & (cum_nc > 0)
        lift[valid] = cum_yt[valid] / cum_nt[valid] - cum_yc[valid] / cum_nc[valid]
        return lift

    lift_v, lift_c = cum_lift("visit"), cum_lift("conversion")
    rows = []
    for share in np.arange(step, 1 + step / 2, step):
        k = max(1, int(round(share * n)))
        rows.append(economics(
            share=k / n,
            lift_visit=lift_v[k - 1],
            lift_conversion=lift_c[k - 1],
            n_population=n_population,
            cost=cost,
            value_visit=value_visit,
            value_conversion=value_conversion,
        ))
    return pd.DataFrame(rows)


def profit_max_share(curve: pd.DataFrame) -> float:
    return float(curve.loc[curve["profit"].idxmax(), "share_targeted"])


def profit_at_share(curve: pd.DataFrame, share: float) -> pd.Series:
    """The curve row nearest to `share`. Used to evaluate a cutoff chosen elsewhere."""
    return curve.iloc[(curve["share_targeted"] - share).abs().argmin()]


def policy_table(test: pd.DataFrame, n_population: int, econ: dict, cutoff_share: float) -> pd.DataFrame:
    """Target nobody, target everyone, random 30%, and top-k% by uplift at the valid-chosen cutoff."""
    cost, v_visit, v_conv = econ["cost_per_treated"], econ["value_per_visit"], econ["value_per_conversion"]
    n = len(test)
    rng = np.random.default_rng(RANDOM_SEED)
    random_mask = np.zeros(n, dtype=bool)
    random_mask[rng.choice(n, size=int(round(RANDOM_SHARE * n)), replace=False)] = True

    k = max(1, int(round(cutoff_share * n)))
    top_k_mask = (test["tau"].rank(method="first", ascending=False) <= k).to_numpy()

    policies = {
        "target_nobody": np.zeros(n, dtype=bool),
        "target_everyone": np.ones(n, dtype=bool),
        f"random_{int(RANDOM_SHARE * 100)}pct": random_mask,
        f"top_{cutoff_share * 100:.1f}pct_by_uplift": top_k_mask,
    }
    rows = [{"policy": name, **policy_outcome(test, mask, n_population, cost, v_visit, v_conv)}
            for name, mask in policies.items()]
    return pd.DataFrame(rows)


def sensitivity_grid(valid: pd.DataFrame, test: pd.DataFrame, n_population: int, econ: dict) -> pd.DataFrame:
    """For each cost x value-per-conversion cell: the cutoff chosen on valid, and its profit on test."""
    rows = []
    for cost in econ["sensitivity"]["cost_per_treated"]:
        for v_conv in econ["sensitivity"]["value_per_conversion"]:
            valid_curve = budget_curve(valid, n_population, cost, econ["value_per_visit"], v_conv)
            share = profit_max_share(valid_curve)
            test_curve = budget_curve(test, n_population, cost, econ["value_per_visit"], v_conv)
            on_test = profit_at_share(test_curve, share)
            rows.append({
                "cost_per_treated": cost,
                "value_per_conversion": v_conv,
                "cutoff_chosen_on_valid": share,
                "test_profit_at_cutoff": on_test["profit"],
                "test_roi_at_cutoff": on_test["roi"],
                "test_profit_target_everyone": test_curve.iloc[-1]["profit"],
                "test_profit_positive_at_cutoff": bool(on_test["profit"] > 0),
            })
    return pd.DataFrame(rows)


def headline(curve: pd.DataFrame, share: float) -> dict:
    """Share of incremental conversions kept, and share of cost, at a given targeting share."""
    full = curve.iloc[-1]
    row = profit_at_share(curve, share)
    return {
        "share_targeted": float(row["share_targeted"]),
        "pct_incremental_conversions_kept": float(row["incremental_conversions"] / full["incremental_conversions"]),
        "pct_of_cost": float(row["cost"] / full["cost"]),
    }


def main() -> None:
    METRICS_DIR.mkdir(parents=True, exist_ok=True)
    econ = yaml.safe_load(ECON_PATH.read_text(encoding="utf-8"))
    n_population = json.loads(DQ_PATH.read_text(encoding="utf-8"))["source_rows"]
    valid = pd.read_parquet(VALID_SCORES_PATH)
    test = pd.read_parquet(SCORES_PATH)
    print(f"valid rows={len(valid):,}  test rows={len(test):,}  population={n_population:,}")

    cost, v_visit, v_conv = econ["cost_per_treated"], econ["value_per_visit"], econ["value_per_conversion"]
    valid_curve = budget_curve(valid, n_population, cost, v_visit, v_conv)
    cutoff = profit_max_share(valid_curve)
    print(f"cutoff chosen on valid (profit-max): {cutoff:.3f}")

    print("== Policies (test split, cutoff from valid) ==")
    policies = policy_table(test, n_population, econ, cutoff)
    policies.to_csv(METRICS_DIR / "policy_comparison.csv", index=False)
    print(policies.to_string(index=False))

    print("== Budget curve (test split) ==")
    curve = budget_curve(test, n_population, cost, v_visit, v_conv)
    curve.to_csv(METRICS_DIR / "budget_curve.csv", index=False)
    at_cutoff = profit_at_share(curve, cutoff)
    print(f"test profit at valid cutoff {cutoff:.3f}: {at_cutoff['profit']:.0f}, ROI {at_cutoff['roi']:.3f}")
    print(f"test profit-max share (for reference, in-sample): {profit_max_share(curve):.3f}")

    print("== Sensitivity (cutoff from valid, profit on test) ==")
    sens = sensitivity_grid(valid, test, n_population, econ)
    sens.to_csv(METRICS_DIR / "sensitivity.csv", index=False)
    print(sens.to_string(index=False))

    segs = pd.read_csv(METRICS_DIR / "segment_profile.csv").set_index("segment")["share"]
    wasted_share = float(segs.get("sure_thing", 0) + segs.get("lost_cause", 0))
    result = {
        "population": n_population,
        "cutoff_chosen_on_valid": cutoff,
        "policy_comparison": policies.to_dict(orient="records"),
        "test_profit_at_valid_cutoff": float(at_cutoff["profit"]),
        "test_roi_at_valid_cutoff": float(at_cutoff["roi"]),
        "test_profit_max_share_in_sample": profit_max_share(curve),
        "headline_top_20pct": headline(curve, 0.20),
        "target_everyone_wasted_spend_share": wasted_share,
        "sensitivity_cutoff_range": [float(sens["cutoff_chosen_on_valid"].min()), float(sens["cutoff_chosen_on_valid"].max())],
        "sensitivity_target_everyone_negative_cells": int((sens["test_profit_target_everyone"] < 0).sum()),
    }
    (METRICS_DIR / "roi.json").write_text(json.dumps(result, indent=2, default=float), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "policy_comparison"}, indent=2, default=float))


if __name__ == "__main__":
    main()
