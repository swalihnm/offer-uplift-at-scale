"""Download the Criteo Uplift v2.1 file and write it to the bronze layer as Parquet."""

import hashlib
import urllib.request
from pathlib import Path

from pyspark.sql import SparkSession
from pyspark.sql import types as T

from oua.spark import DATA_DIR, ROOT

SOURCE_URL = (
    "https://github.com/jszymon/uplift_sklearn_data/releases/download/"
    "Criteo/criteo-research-uplift-v2.1.csv.gz"
)
SOURCE_SHA256 = "2716e1bf0fd157a93b5bf86924d9088419dfbac2022c6cd90030220634f616dc"
RAW_PATH = ROOT / "data" / "raw" / "criteo-uplift-v2.1.csv.gz"
BRONZE_PATH = DATA_DIR / "bronze" / "criteo"

FEATURES = [f"f{i}" for i in range(12)]

# Explicit schema, so the bronze layer never depends on type inference.
BRONZE_SCHEMA = T.StructType(
    [T.StructField(f, T.DoubleType(), True) for f in FEATURES]
    + [
        T.StructField("treatment", T.IntegerType(), True),
        T.StructField("conversion", T.IntegerType(), True),
        T.StructField("visit", T.IntegerType(), True),
        T.StructField("exposure", T.IntegerType(), True),
    ]
)


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_raw_file() -> Path:
    """Download the raw file if missing, then verify its checksum."""
    RAW_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not RAW_PATH.exists():
        print(f"Downloading {SOURCE_URL} ...")
        urllib.request.urlretrieve(SOURCE_URL, RAW_PATH)
    actual = sha256_of(RAW_PATH)
    if actual != SOURCE_SHA256:
        raise RuntimeError(f"Checksum mismatch for {RAW_PATH}: {actual}")
    return RAW_PATH


def ingest(spark: SparkSession) -> int:
    """Raw CSV -> bronze Parquet. Returns the bronze row count."""
    raw = ensure_raw_file()
    df = (
        spark.read.option("header", True)
        .schema(BRONZE_SCHEMA)
        .csv(raw.as_posix())
    )
    df.write.mode("overwrite").parquet(BRONZE_PATH.as_posix())
    return spark.read.parquet(BRONZE_PATH.as_posix()).count()
