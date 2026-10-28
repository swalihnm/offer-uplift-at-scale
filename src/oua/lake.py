"""Bronze -> silver -> gold, Hive tables, and data-quality checks.

Run:  python -m oua.lake
"""

import json
import time
from pathlib import Path

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.window import Window

from oua.ingest import BRONZE_PATH, RAW_PATH, ingest
from oua.spark import DATA_DIR, ROOT, get_spark, run_hql

FEATURES = [f"f{i}" for i in range(12)]
ALL_COLS = FEATURES + ["treatment", "conversion", "visit", "exposure"]
SILVER_PATH = DATA_DIR / "silver" / "criteo"
HIVE_DIR = ROOT / "sql" / "hive"
METRICS_DIR = ROOT / "outputs" / "metrics"

SPLIT_SHARES = {"train": 0.70, "valid": 0.15, "test": 0.15}


def build_silver(bronze: DataFrame) -> DataFrame:
    """Drop null outcomes, add a unique user_id, a stratified split and a hash bucket.

    Identical rows are KEPT as separate users. An earlier version dropped them, and that removed
    about 10% of treated rows but only about 2% of control rows, which broke randomization (SRM).
    Each repeat gets an occurrence index, so user_id stays unique.
    """
    no_null_outcomes = bronze.dropna(subset=["treatment", "visit", "conversion"])
    occurrence = F.row_number().over(Window.partitionBy(*ALL_COLS).orderBy(*ALL_COLS)) - 1

    with_id = (
        no_null_outcomes.withColumn("_occ", occurrence)
        .withColumn(
            "user_id",
            F.sha2(
                F.concat_ws("|", *[F.col(c).cast("string") for c in ALL_COLS], F.col("_occ").cast("string")),
                256,
            ),
        )
        .drop("_occ")
        .withColumn("bucket", F.pmod(F.crc32("user_id"), F.lit(100)).cast("int"))
    )

    # Stratified split: within each treatment x visit stratum, rank rows by a
    # stable hash and cut the ranks at 70% / 85%. This gives exact shares per stratum.
    stratum = Window.partitionBy("treatment", "visit")
    ranked = with_id.withColumn(
        "_rank",
        (F.row_number().over(stratum.orderBy("user_id")) - 1)
        / F.count(F.lit(1)).over(stratum),
    )
    silver = ranked.withColumn(
        "split",
        F.when(F.col("_rank") < SPLIT_SHARES["train"], F.lit("train"))
        .when(
            F.col("_rank") < SPLIT_SHARES["train"] + SPLIT_SHARES["valid"],
            F.lit("valid"),
        )
        .otherwise(F.lit("test")),
    ).drop("_rank")

    return silver


def write_silver(spark: SparkSession) -> DataFrame:
    silver = build_silver(spark.table("oua.bronze_criteo")).cache()
    silver.write.mode("overwrite").partitionBy("split").parquet(SILVER_PATH.as_posix())
    return spark.read.parquet(SILVER_PATH.as_posix())


def dq_checks(spark: SparkSession, silver: DataFrame) -> dict:
    """Row count vs source, null outcomes, treatment share, split totals."""
    bronze = spark.table("oua.bronze_criteo")
    source_rows = spark.read.text(RAW_PATH.as_posix()).count() - 1  # minus header

    counts = bronze.agg(
        F.count(F.lit(1)).alias("bronze_rows"),
        F.sum(F.col("visit").isNull().cast("int")).alias("null_visit"),
        F.sum(F.col("conversion").isNull().cast("int")).alias("null_conversion"),
        F.avg("treatment").alias("treatment_share"),
    ).collect()[0]

    silver_rows = silver.count()
    split_counts = {r["split"]: r["n"] for r in silver.groupBy("split").agg(F.count(F.lit(1)).alias("n")).collect()}
    distinct_bronze_rows = bronze.dropDuplicates(ALL_COLS).count()

    report = {
        "source_rows": source_rows,
        "bronze_rows": counts["bronze_rows"],
        "bronze_matches_source": counts["bronze_rows"] == source_rows,
        "null_visit": counts["null_visit"],
        "null_conversion": counts["null_conversion"],
        "treatment_share": round(counts["treatment_share"], 4),
        "treatment_share_ok": abs(counts["treatment_share"] - 0.85) < 0.02,
        "exact_duplicate_rows_kept": counts["bronze_rows"] - distinct_bronze_rows,
        "silver_rows": silver_rows,
        "silver_user_ids_unique": silver.select("user_id").distinct().count() == silver_rows,
        "split_counts": split_counts,
        "split_total_matches_silver": sum(split_counts.values()) == silver_rows,
    }
    return report


def benchmark_cache(spark: SparkSession, silver: DataFrame) -> dict:
    """Before/after timing for caching: the gold build reads silver several times."""

    def three_passes(df: DataFrame) -> float:
        start = time.perf_counter()
        for col in ["visit", "conversion", "exposure"]:
            df.groupBy("treatment").agg(F.avg(col)).collect()
        return round(time.perf_counter() - start, 2)

    before = three_passes(spark.read.parquet(SILVER_PATH.as_posix()))
    cached = spark.read.parquet(SILVER_PATH.as_posix()).cache()
    cached.count()  # materialise the cache before timing
    after = three_passes(cached)
    cached.unpersist()
    return {"seconds_without_cache": before, "seconds_with_cache": after}


def build_gold(spark: SparkSession) -> None:
    run_hql(spark, HIVE_DIR / "gold_experiment_summary.hql")
    run_hql(spark, HIVE_DIR / "gold_balance_check.hql")
    run_hql(spark, HIVE_DIR / "gold_bucket_metrics.hql")


def register_tables(spark: SparkSession) -> None:
    run_hql(
        spark,
        HIVE_DIR / "ddl_bronze.hql",
        bronze_location=BRONZE_PATH.as_posix(),
    )
    run_hql(
        spark,
        HIVE_DIR / "ddl_silver.hql",
        silver_location=SILVER_PATH.as_posix(),
    )


def main() -> None:
    spark = get_spark("oua-lake")
    METRICS_DIR.mkdir(parents=True, exist_ok=True)

    print("== Ingest (bronze) ==")
    ingest(spark)
    register_tables(spark)

    print("== Silver ==")
    silver = write_silver(spark)
    spark.sql("MSCK REPAIR TABLE oua.silver_criteo")

    print("== DQ checks ==")
    dq = dq_checks(spark, silver)
    print(json.dumps(dq, indent=2))

    print("== Cache benchmark ==")
    bench = benchmark_cache(spark, silver)
    print(json.dumps(bench, indent=2))

    print("== Gold ==")
    build_gold(spark)
    summary = spark.table("oua.gold_experiment_summary").toPandas()
    print(summary.to_string(index=False))

    (METRICS_DIR / "dq.json").write_text(json.dumps(dq, indent=2), encoding="utf-8")
    (METRICS_DIR / "cache_benchmark.json").write_text(json.dumps(bench, indent=2), encoding="utf-8")
    spark.stop()


if __name__ == "__main__":
    main()
