"""Run the analysis queries in sql/bigquery/ against the offer_uplift dataset and save the results.

Needs GCP_PROJECT and application-default credentials (see README). Results go to outputs/bigquery/.

Run:  GCP_PROJECT=<project> python -m oua.bq_queries
"""

import os

from google.cloud import bigquery

from oua.spark import ROOT

SQL_DIR = ROOT / "sql" / "bigquery"
OUT_DIR = ROOT / "outputs" / "bigquery"
QUERIES = ["decile_lift", "cumulative_gain", "policy_ranking", "segment_waste"]


def main() -> None:
    project = os.environ.get("GCP_PROJECT")
    if not project:
        raise SystemExit("Set GCP_PROJECT to your Google Cloud project id.")
    client = bigquery.Client(project=project)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name in QUERIES:
        sql = (SQL_DIR / f"{name}.sql").read_text(encoding="utf-8")
        df = client.query(sql).result().to_dataframe()
        df.to_csv(OUT_DIR / f"{name}.csv", index=False)
        print(f"== {name} ({len(df)} rows)")
        print(df.to_string(index=False))


if __name__ == "__main__":
    main()
