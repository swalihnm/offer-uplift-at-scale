"""Load the result marts into BigQuery (dataset `offer_uplift`).

Prerequisites (manual): a Google Cloud project with the BigQuery sandbox enabled, and
`gcloud auth application-default login`. Set GCP_PROJECT to the project id.

Run:  GCP_PROJECT=my-project python -m oua.bq_load
"""

import os

import pandas as pd
from google.cloud import bigquery

from oua.spark import ROOT

EXTRACT_DIR = ROOT / "tableau" / "extracts"
DATASET = "offer_uplift"
TABLES = [
    "experiment_summary",
    "uplift_deciles",
    "policy_comparison",
    "budget_curve",
    "segment_profile",
    "power_table",
    "balance_smd",
    "shap_importance",
    "sensitivity",
]


def main() -> None:
    project = os.environ.get("GCP_PROJECT")
    if not project:
        raise SystemExit("Set GCP_PROJECT to your Google Cloud project id.")
    client = bigquery.Client(project=project)
    client.create_dataset(bigquery.Dataset(f"{project}.{DATASET}"), exists_ok=True)

    for name in TABLES:
        df = pd.read_csv(EXTRACT_DIR / f"{name}.csv")
        table_id = f"{project}.{DATASET}.{name}"
        job = client.load_table_from_dataframe(
            df, table_id, job_config=bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE")
        )
        job.result()
        print(f"loaded {len(df):,} rows -> {table_id}")


if __name__ == "__main__":
    main()
