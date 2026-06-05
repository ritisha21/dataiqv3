"""
Feature Store — Dask-aware
───────────────────────────
For DataFrames under DASK_THRESHOLD rows  → pure pandas (fast, no overhead)
For DataFrames over  DASK_THRESHOLD rows  → Dask map_partitions (memory-safe)

compute() is called exactly once, at the end, so callers always get a pandas
DataFrame back — no Dask objects leak out of this module.
"""

from __future__ import annotations

import hashlib
import json
from typing import Dict, List, Any, Optional, Tuple

import numpy as np
import pandas as pd
import dask.dataframe as dd

from app.core.logging import get_logger

logger = get_logger(__name__)

DASK_THRESHOLD = 100_000   # rows — above this we use Dask transforms


class FeatureStoreService:

    def build_features(
        self,
        df:               pd.DataFrame,
        semantic_mapping: Dict[str, Any],
        table_name:       str,
        target_col:       Optional[str] = None,
        window_cols:      Optional[List[str]] = None,
    ) -> Tuple[pd.DataFrame, List[Dict]]:
        """
        Returns (feature_df, feature_definitions_list).
        Uses Dask internally for large DataFrames.
        """
        use_dask = len(df) > DASK_THRESHOLD
        logger.info(
            "feature_store_build",
            rows=len(df), use_dask=use_dask, table=table_name
        )

        if use_dask:
            return self._build_features_dask(df, semantic_mapping, table_name, target_col, window_cols)
        else:
            return self._build_features_pandas(df, semantic_mapping, table_name, target_col, window_cols)

    # ── Dask path ─────────────────────────────────────────────────────────────

    def _build_features_dask(
        self,
        df:               pd.DataFrame,
        semantic_mapping: Dict,
        table_name:       str,
        target_col:       Optional[str],
        window_cols:      Optional[List[str]],
    ) -> Tuple[pd.DataFrame, List[Dict]]:
        definitions: List[Dict] = []

        npartitions = max(2, len(df) // 100_000)
        ddf = dd.from_pandas(df, npartitions=npartitions)

        col_tags = {}
        if semantic_mapping and table_name in semantic_mapping.get("tables", {}):
            col_tags = semantic_mapping["tables"][table_name].get("columns", {})

        # 1. Drop ID columns
        id_cols = [c for c, info in col_tags.items()
                   if info["tag"] == "id" and c in ddf.columns]
        if id_cols:
            ddf = ddf.drop(columns=id_cols, errors="ignore")

        # 2. Datetime expansion (lazy via map_partitions)
        dt_cols = [
            c for c, info in col_tags.items()
            if info["tag"] == "datetime" and c in ddf.columns
        ]
        for col in dt_cols:
            try:
                meta = ddf._meta.copy()
                for suffix in ("_year","_month","_dayofweek","_hour"):
                    meta[f"{col}{suffix}"] = pd.Series(dtype="float32")

                ddf = ddf.map_partitions(_expand_dt_partition, col, meta=meta)
                ddf = ddf.drop(columns=[col], errors="ignore")
                definitions.append({
                    "name":           f"{col}_temporal",
                    "feature_type":   "temporal",
                    "source_columns": [col],
                    "source_table":   table_name,
                    "lineage":        {"transformation": "datetime_decomposition"},
                })
            except Exception as exc:
                logger.warning("dt_expand_failed_dask", col=col, error=str(exc))
                ddf = ddf.drop(columns=[col], errors="ignore")

        # 3. Categorical encoding (frequency, lazy)
        obj_cols = [
            c for c in ddf.select_dtypes(include=["object"]).columns
            if c != target_col
        ]
        for col in obj_cols:
            try:
                nunique = ddf[col].nunique().compute()
                if nunique <= 50:
                    freq_map = ddf[col].value_counts(normalize=True).compute().to_dict()
                    new_meta = ddf._meta.assign(**{col: 0.0})
                    ddf = ddf.map_partitions(_freq_encode_partition, col, freq_map, meta=new_meta)
                else:
                    # High cardinality → drop
                    ddf = ddf.drop(columns=[col], errors="ignore")
                definitions.append({
                    "name":           f"{col}_encoded",
                    "feature_type":   "categorical",
                    "source_columns": [col],
                    "source_table":   table_name,
                    "lineage":        {"transformation": "frequency_encoding"},
                })
            except Exception as exc:
                logger.warning("cat_encode_failed_dask", col=col, error=str(exc))
                ddf = ddf.drop(columns=[col], errors="ignore")

        # 4. Fill numeric NaNs (lazy fillna)
        num_cols = [c for c in ddf.select_dtypes(include=[np.number]).columns
                    if c != target_col]
        if num_cols:
            medians = ddf[num_cols].quantile(0.5).compute()
            fill_map = {c: float(medians[c]) for c in num_cols if c in medians}
            ddf = ddf.fillna(fill_map)

        # 5. Single compute() call — materialise to pandas
        result_df = ddf.compute()

        return result_df, definitions

    # ── Pandas path (small data) ──────────────────────────────────────────────

    def _build_features_pandas(
        self,
        df:               pd.DataFrame,
        semantic_mapping: Dict,
        table_name:       str,
        target_col:       Optional[str],
        window_cols:      Optional[List[str]],
    ) -> Tuple[pd.DataFrame, List[Dict]]:
        feature_df  = df.copy()
        definitions: List[Dict] = []

        col_tags = {}
        if semantic_mapping and table_name in semantic_mapping.get("tables", {}):
            col_tags = semantic_mapping["tables"][table_name].get("columns", {})

        # Drop ID cols
        id_cols = [c for c, info in col_tags.items()
                   if info["tag"] == "id" and c in feature_df.columns]
        feature_df = feature_df.drop(columns=id_cols, errors="ignore")

        # Datetime expansion
        dt_cols = [
            c for c, info in col_tags.items()
            if info["tag"] == "datetime" and c in feature_df.columns
        ]
        for col in dt_cols:
            try:
                dt = pd.to_datetime(feature_df[col], errors="coerce")
                feature_df[f"{col}_year"]      = dt.dt.year.astype("float32")
                feature_df[f"{col}_month"]     = dt.dt.month.astype("float32")
                feature_df[f"{col}_dayofweek"] = dt.dt.dayofweek.astype("float32")
                feature_df[f"{col}_hour"]      = dt.dt.hour.astype("float32")
                feature_df = feature_df.drop(columns=[col], errors="ignore")
                definitions.append({
                    "name": f"{col}_temporal", "feature_type": "temporal",
                    "source_columns": [col], "source_table": table_name,
                    "lineage": {"transformation": "datetime_decomposition"},
                })
            except Exception as exc:
                logger.warning("dt_expand_failed", col=col, error=str(exc))
                feature_df = feature_df.drop(columns=[col], errors="ignore")

        # Categorical encoding
        for col in feature_df.select_dtypes(include=["object","category"]).columns:
            if target_col and col == target_col:
                continue
            nunique = feature_df[col].nunique()
            if nunique <= 50:
                freq_map = feature_df[col].value_counts(normalize=True).to_dict()
                feature_df[col] = feature_df[col].map(freq_map).fillna(0.0)
                definitions.append({
                    "name": f"{col}_freq", "feature_type": "categorical",
                    "source_columns": [col], "source_table": table_name,
                    "lineage": {"transformation": "frequency_encoding"},
                })
            else:
                feature_df = feature_df.drop(columns=[col], errors="ignore")

        # Fill numeric NaNs
        for col in feature_df.select_dtypes(include=[np.number]).columns:
            if target_col and col == target_col:
                continue
            feature_df[col] = feature_df[col].fillna(feature_df[col].median())

        # Window aggregations
        if window_cols:
            for col in window_cols:
                if col in feature_df.columns:
                    for w in [3, 7, 30]:
                        feature_df[f"{col}_roll{w}"] = (
                            feature_df[col].rolling(w, min_periods=1).mean()
                        )
                    definitions.append({
                        "name": f"{col}_windows", "feature_type": "window",
                        "source_columns": [col], "source_table": table_name,
                        "lineage": {"transformation": "rolling_window", "windows": [3,7,30]},
                    })

        return feature_df, definitions

    # ── utilities ─────────────────────────────────────────────────────────────

    def compute_dataset_hash(self, df: pd.DataFrame) -> str:
        shape_str  = f"{df.shape[0]}_{df.shape[1]}"
        cols_str   = "_".join(sorted(df.columns.tolist()))
        sample_str = df.head(100).to_csv()
        return hashlib.sha256(
            f"{shape_str}|{cols_str}|{sample_str}".encode()
        ).hexdigest()[:16]

    def get_feature_names(
        self, feature_df: pd.DataFrame, target_col: Optional[str]
    ) -> List[str]:
        cols = feature_df.columns.tolist()
        if target_col and target_col in cols:
            cols.remove(target_col)
        return cols


# ── partition-level helpers (must be top-level for Dask pickle) ───────────────

def _expand_dt_partition(partition: pd.DataFrame, col: str) -> pd.DataFrame:
    partition = partition.copy()
    try:
        dt = pd.to_datetime(partition[col], errors="coerce")
        partition[f"{col}_year"]      = dt.dt.year.astype("float32")
        partition[f"{col}_month"]     = dt.dt.month.astype("float32")
        partition[f"{col}_dayofweek"] = dt.dt.dayofweek.astype("float32")
        partition[f"{col}_hour"]      = dt.dt.hour.astype("float32")
    except Exception:
        pass
    return partition


def _freq_encode_partition(
    partition: pd.DataFrame, col: str, freq_map: dict
) -> pd.DataFrame:
    partition = partition.copy()
    partition[col] = partition[col].map(freq_map).fillna(0.0).astype("float32")
    return partition


feature_store = FeatureStoreService()
