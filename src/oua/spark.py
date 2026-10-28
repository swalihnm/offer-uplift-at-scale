"""SparkSession factory shared by every pipeline step."""

import os
from pathlib import Path

from pyspark.sql import SparkSession

ROOT = Path(__file__).resolve().parents[2]
# Spark writes Parquet and chmods its files, which fails on NTFS mounts such as /mnt/c under WSL.
# Set OUA_DATA_DIR to a Linux-filesystem path to move the Spark data there. Defaults to ROOT/data.
DATA_DIR = Path(os.environ.get("OUA_DATA_DIR", ROOT / "data"))
WAREHOUSE_DIR = DATA_DIR / "warehouse"
METASTORE_DIR = DATA_DIR / "metastore_db"


def get_spark(app_name: str = "oua", shuffle_partitions: int = 16) -> SparkSession:
    """Local-mode Spark session with Hive support and a local Derby metastore."""
    spark = (
        SparkSession.builder.appName(app_name)
        .master("local[*]")
        .config("spark.sql.shuffle.partitions", shuffle_partitions)
        .config("spark.driver.memory", "3g")
        .config("spark.sql.warehouse.dir", WAREHOUSE_DIR.as_posix())
        .config(
            "spark.hadoop.javax.jdo.option.ConnectionURL",
            f"jdbc:derby:;databaseName={METASTORE_DIR.as_posix()};create=true",
        )
        .enableHiveSupport()
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")
    return spark


def run_hql(spark: SparkSession, path: Path, **params: str) -> None:
    """Run a HiveQL file. `${name}` placeholders are filled from params."""
    text = path.read_text(encoding="utf-8")
    for key, value in params.items():
        text = text.replace("${" + key + "}", value)
    for statement in text.split(";"):
        lines = [ln for ln in statement.splitlines() if not ln.strip().startswith("--")]
        cleaned = "\n".join(lines).strip()
        if cleaned:
            spark.sql(cleaned)
