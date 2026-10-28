# Data

**Source:** Criteo AI Lab, "Criteo Uplift Prediction Dataset", v2.1 (`criteo-research-uplift-v2.1.csv.gz`).
Official page: https://ailab.criteo.com/criteo-uplift-prediction-dataset/

**Download used:** GitHub mirror `https://github.com/jszymon/uplift_sklearn_data/releases/download/Criteo/criteo-research-uplift-v2.1.csv.gz`
- Download date: 2026-10-27
- SHA-256: `2716e1bf0fd157a93b5bf86924d9088419dfbac2022c6cd90030220634f616dc` (verified)
- Size: 311,422,618 bytes (compressed)

**Rows:** 13,979,592 (one per user, verified by line count).

**Columns:** `f0`–`f11` (12 anonymized dense features), `treatment` (1 = targeted with ads), `conversion`, `visit`, `exposure`.

**Caveat:** The features are anonymized, so any segments are data-driven clusters, not demographics.
