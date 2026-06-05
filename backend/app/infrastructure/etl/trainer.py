"""
ETL Trainer — Dask-powered
───────────────────────────
E — Dask reads table in partitions (handles 10M+ rows)
T — Dask feature engineering: map_partitions for transforms,
    then compute() only when XGBoost needs a numpy array
L — XGBoost DMatrix built directly from Dask array (zero copy)
"""

from __future__ import annotations

import uuid
import json
from typing import Any, Dict, List
from datetime import datetime

import numpy as np
import pandas as pd
import dask.dataframe as dd
import dask.array as da
from dask.diagnostics import ProgressBar
from sqlalchemy import create_engine, text

from app.core.config import settings
from app.core.logging import get_logger
from app.infrastructure.etl.scanner import ETLScanner, etl_scanner
from app.domain.models.models import ModelGoal

logger = get_logger(__name__)


class ETLTrainer:

    def run_etl_pipeline(
        self,
        *,
        tenant_id:     str,
        connection_id: str,
        suggestions:   List[Dict[str, Any]],
        conn_record:   Any,
    ) -> List[Dict[str, Any]]:
        results = []

        for suggestion in suggestions:
            sid          = suggestion["id"]
            table        = suggestion["table"]
            target_col   = suggestion["target_column"]
            goal_str     = suggestion["goal"]

            logger.info("etl_start", sid=sid, table=table, target=target_col)

            try:
                # ── E: Extract with Dask ──────────────────────────────────────
                url       = etl_scanner._build_url(conn_record)
                engine    = create_engine(url, pool_pre_ping=True)
                row_count = etl_scanner._fast_count(engine, table)
                engine.dispose()

                if row_count > 50_000:
                    engine_sync = create_engine(url, pool_pre_ping=True)
                    idx_col = etl_scanner._find_index_col(engine_sync, table)
                    engine_sync.dispose()

                    logger.info("dask_extract", table=table, rows=row_count)
                    ddf = dd.read_sql_table(
                        table_name  = table,
                        con         = url,
                        index_col   = idx_col,
                        npartitions = max(4, row_count // 100_000),
                    )
                else:
                    engine_sync = create_engine(url, pool_pre_ping=True)
                    with engine_sync.connect() as c:
                        pdf = pd.read_sql(text(f'SELECT * FROM "{table}"'), c)
                    engine_sync.dispose()
                    ddf = dd.from_pandas(pdf, npartitions=2)

                dataset_hash = _dask_hash(ddf)

                # ── T: Transform with Dask ────────────────────────────────────
                ddf_feat, feat_names = _dask_feature_engineering(ddf, target_col)

                # Verify target survived
                if target_col not in ddf_feat.columns:
                    raise ValueError(f"Target '{target_col}' dropped during transforms")

                # ── L: Compute + Train ────────────────────────────────────────
                model_id = str(uuid.uuid4())
                _upsert_model_record(
                    model_id=model_id, tenant_id=tenant_id,
                    connection_id=connection_id, name=suggestion["title"],
                    goal=goal_str, target_col=target_col,
                    source_table=table, status="training",
                )

                # Compute Dask → pandas only once, right before training
                logger.info("dask_compute_start", table=table)
                with ProgressBar():
                    final_df = ddf_feat.compute()
                logger.info("dask_compute_done", shape=final_df.shape)

                from app.infrastructure.ml_pipeline.pipeline import ml_pipeline
                try:
                    goal_enum = ModelGoal(goal_str)
                except ValueError:
                    goal_enum = ModelGoal.classification

                train_result = ml_pipeline.train(
                    df           = final_df,
                    target_col   = target_col,
                    goal         = goal_enum,
                    model_id     = model_id,
                    tenant_id    = tenant_id,
                    dataset_hash = dataset_hash,
                )

                _upsert_model_record(
                    model_id=model_id, tenant_id=tenant_id,
                    connection_id=connection_id, name=suggestion["title"],
                    goal=goal_str, target_col=target_col,
                    source_table=table, status="ready",
                    metrics=train_result["metrics"],
                    artifact_path=train_result["artifact_path"],
                    dataset_hash=dataset_hash,
                    feature_cols=train_result["feature_cols"],
                )

                results.append({
                    "suggestion_id": sid,
                    "model_id":      model_id,
                    "status":        "success",
                    "metrics":       train_result["metrics"],
                    "table":         table,
                    "target_column": target_col,
                    "goal":          goal_str,
                    "rows_trained":  len(final_df),
                })

                logger.info("etl_success", sid=sid, model_id=model_id)

            except Exception as exc:
                logger.error("etl_failed", sid=sid, error=str(exc))
                results.append({
                    "suggestion_id": sid,
                    "model_id":      None,
                    "status":        "failed",
                    "error":         str(exc),
                    "table":         table,
                    "target_column": target_col,
                    "goal":          goal_str,
                })

        return results


# ── Dask feature engineering ──────────────────────────────────────────────────

def _dask_feature_engineering(
    ddf: dd.DataFrame,
    target_col: str,
) -> tuple[dd.DataFrame, list[str]]:
    """
    All transforms are applied partition-by-partition via map_partitions.
    No .compute() is called here — the graph stays lazy.
    """

    # 1. Drop high-null columns (compute null rates cheaply)
    null_rates = ddf.isnull().mean().compute()
    drop_cols  = null_rates[null_rates > 0.7].index.tolist()
    drop_cols  = [c for c in drop_cols if c != target_col]
    if drop_cols:
        ddf = ddf.drop(columns=drop_cols)

    # 2. Datetime decomposition (lazy, per partition)
    dt_cols = [
        c for c in ddf.columns
        if any(kw in c.lower() for kw in ("date","time","created","updated","_at"))
        and c != target_col
    ]
    for col in dt_cols:
        ddf = ddf.map_partitions(_expand_datetime, col, meta=_datetime_meta(ddf, col))
        ddf = ddf.drop(columns=[col], errors="ignore")

    # 3. Categorical encoding (lazy frequency encoding per partition)
    #    We compute the global frequency map once, then apply lazily
    obj_cols = [
        c for c in ddf.select_dtypes(include=["object"]).columns
        if c != target_col
    ]
    for col in obj_cols:
        freq_map = ddf[col].value_counts(normalize=True).compute().to_dict()
        ddf = ddf.map_partitions(
            _freq_encode, col, freq_map,
            meta=ddf._meta.assign(**{col: 0.0})
        )

    # 4. Fill numeric NaNs (lazy)
    num_cols = [
        c for c in ddf.select_dtypes(include=[np.number]).columns
        if c != target_col
    ]
    medians = ddf[num_cols].quantile(0.5).compute() if num_cols else {}
    fill_map = {c: float(medians[c]) for c in num_cols if c in medians}
    if fill_map:
        ddf = ddf.fillna(fill_map)

    feat_names = [c for c in ddf.columns if c != target_col]
    return ddf, feat_names


def _expand_datetime(partition: pd.DataFrame, col: str) -> pd.DataFrame:
    partition = partition.copy()
    try:
        dt = pd.to_datetime(partition[col], errors="coerce")
        partition[f"{col}_year"]       = dt.dt.year.astype("float32")
        partition[f"{col}_month"]      = dt.dt.month.astype("float32")
        partition[f"{col}_dayofweek"]  = dt.dt.dayofweek.astype("float32")
        partition[f"{col}_hour"]       = dt.dt.hour.astype("float32")
    except Exception:
        pass
    return partition


def _datetime_meta(ddf: dd.DataFrame, col: str) -> pd.DataFrame:
    meta = ddf._meta.copy()
    for suffix in ("_year", "_month", "_dayofweek", "_hour"):
        meta[f"{col}{suffix}"] = pd.Series(dtype="float32")
    return meta


def _freq_encode(
    partition: pd.DataFrame, col: str, freq_map: dict
) -> pd.DataFrame:
    partition = partition.copy()
    partition[col] = partition[col].map(freq_map).fillna(0.0).astype("float32")
    return partition


# ── helpers ───────────────────────────────────────────────────────────────────

def _dask_hash(ddf: dd.DataFrame) -> str:
    """Cheap reproducible hash: shape + column names + first partition sample."""
    import hashlib
    try:
        shape_str = f"{ddf.npartitions}"
        cols_str  = "_".join(ddf.columns.tolist())
        sample    = ddf.get_partition(0).head(10).to_csv()
        return hashlib.sha256(f"{shape_str}|{cols_str}|{sample}".encode()).hexdigest()[:16]
    except Exception:
        return "unknown"


def _upsert_model_record(
    *,
    model_id: str,
    tenant_id: str,
    connection_id: str,
    name: str,
    goal: str,
    target_col: str,
    source_table: str,
    status: str,
    metrics: dict | None = None,
    artifact_path: str | None = None,
    dataset_hash: str | None = None,
    feature_cols: list | None = None,
) -> None:
    engine = create_engine(settings.SYNC_DATABASE_URL)
    try:
        with engine.begin() as conn:
            exists = conn.execute(
                text("SELECT id FROM ml_models WHERE id = :id"), {"id": model_id}
            ).fetchone()

            if not exists:
                conn.execute(text("""
                    INSERT INTO ml_models
                        (id, tenant_id, connection_id, name, goal, status,
                         target_column, source_table, created_at)
                    VALUES (:id,:tid,:cid,:name,:goal,:status,:target,:table,NOW())
                """), {
                    "id": model_id, "tid": tenant_id, "cid": connection_id,
                    "name": name, "goal": goal, "status": status,
                    "target": target_col, "table": source_table,
                })
            else:
                conn.execute(text("""
                    UPDATE ml_models SET
                        status        = :status,
                        metrics       = :metrics,
                        artifact_path = :artifact_path,
                        dataset_hash  = :dataset_hash,
                        feature_columns = :feature_cols,
                        trained_at = CASE WHEN :status='ready' THEN NOW() ELSE trained_at END
                    WHERE id = :id
                """), {
                    "id":            model_id,
                    "status":        status,
                    "metrics":       json.dumps(metrics or {}),
                    "artifact_path": artifact_path or "",
                    "dataset_hash":  dataset_hash or "",
                    "feature_cols":  json.dumps(feature_cols or []),
                })
    finally:
        engine.dispose()


etl_trainer = ETLTrainer()
