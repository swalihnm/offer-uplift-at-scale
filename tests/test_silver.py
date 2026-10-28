"""Spark tests for the silver transform (dedupe, null drop, stratified split). Uses a small local session, no Hive."""

import pytest
from chispa import assert_df_equality
from pyspark.sql import SparkSession
from pyspark.sql import functions as F

from oua.ingest import BRONZE_SCHEMA
from oua.lake import build_silver


@pytest.fixture(scope="module")
def spark():
    session = (
        SparkSession.builder.master("local[1]")
        .appName("oua-tests")
        .config("spark.sql.shuffle.partitions", 2)
        .getOrCreate()
    )
    yield session
    session.stop()


def _row(i: int, treatment: int, visit: int | None) -> tuple:
    features = [float(i + k) for k in range(12)]
    return (*features, treatment, 0, visit, 0)


def test_silver_keeps_exact_duplicates_and_drops_null_outcomes(spark):
    rows = [_row(i, i % 2, i % 3 == 0 and 1 or 0) for i in range(40)]
    rows.append(rows[0])                  # exact duplicate -> kept as a separate user
    rows.append(_row(99, 1, None))        # null outcome -> dropped
    bronze = spark.createDataFrame(rows, schema=BRONZE_SCHEMA)

    silver = build_silver(bronze)

    assert silver.count() == 41
    assert silver.filter(F.col("visit").isNull()).count() == 0
    assert silver.select("user_id").distinct().count() == 41


def test_silver_split_is_exact_within_each_stratum(spark):
    rows = [_row(i, i % 2, (i // 2) % 2) for i in range(400)]
    bronze = spark.createDataFrame(rows, schema=BRONZE_SCHEMA)

    silver = build_silver(bronze)
    counts = (
        silver.groupBy("treatment", "visit", "split")
        .agg(F.count(F.lit(1)).alias("n"))
        .collect()
    )
    totals = {}
    for r in counts:
        key = (r["treatment"], r["visit"])
        totals[key] = totals.get(key, 0) + r["n"]
    for r in counts:
        key = (r["treatment"], r["visit"])
        expected = {"train": 0.70, "valid": 0.15, "test": 0.15}[r["split"]] * totals[key]
        assert abs(r["n"] - expected) <= 1.0


def test_silver_output_matches_expected_small_frame(spark):
    rows = [_row(i, 1, 1) for i in range(3)]
    bronze = spark.createDataFrame(rows, schema=BRONZE_SCHEMA)
    silver = build_silver(bronze).select("treatment", "visit", "conversion", "exposure").orderBy("treatment")
    expected = spark.createDataFrame([(1, 1, 0, 0)] * 3, schema="treatment int, visit int, conversion int, exposure int")
    assert_df_equality(silver, expected, ignore_row_order=True)
