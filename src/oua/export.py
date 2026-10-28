"""Write the Tableau extracts (CSV) and the gold experiment summary used by BigQuery and Tableau.

Run:  python -m oua.export
"""

import shutil

from oua.spark import ROOT, get_spark

METRICS_DIR = ROOT / "outputs" / "metrics"
EXTRACT_DIR = ROOT / "tableau" / "extracts"

# Source file in outputs/metrics -> name used by BigQuery and Tableau
EXTRACTS = {
    "balance_smd.csv": "balance_smd.csv",
    "power_table.csv": "power_table.csv",
    "uplift_deciles.csv": "uplift_deciles.csv",
    "segment_profile.csv": "segment_profile.csv",
    "shap_importance.csv": "shap_importance.csv",
    "policy_comparison.csv": "policy_comparison.csv",
    "budget_curve.csv": "budget_curve.csv",
    "sensitivity.csv": "sensitivity.csv",
}


def main() -> None:
    EXTRACT_DIR.mkdir(parents=True, exist_ok=True)
    spark = get_spark("oua-export")
    summary = spark.table("oua.gold_experiment_summary").toPandas()
    summary.to_csv(EXTRACT_DIR / "experiment_summary.csv", index=False)
    print(summary.to_string(index=False))
    spark.stop()

    for src, dst in EXTRACTS.items():
        shutil.copyfile(METRICS_DIR / src, EXTRACT_DIR / dst)
        print(f"copied {src} -> tableau/extracts/{dst}")


if __name__ == "__main__":
    main()
