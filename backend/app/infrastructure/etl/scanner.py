"""
ETL Scanner — Dask-powered
───────────────────────────
Uses Dask DataFrames for all profiling operations so it handles
tables with millions of rows without OOM errors.

Flow:
  1. Read table in partitioned chunks via dask.dataframe.read_sql_table
  2. Compute per-column stats lazily (.describe(), .nunique(), etc.)
  3. Trigger a single .compute() call per table — one pass through data
  4. Return TableProfile + SuggestedFeature lists
"""

from __future__ import annotations

import re
import json
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field, asdict

import numpy as np
import pandas as pd
import dask.dataframe as dd
from sqlalchemy import create_engine, text, inspect

from app.core.security import decrypt_credential
from app.domain.models.models import DBConnection, DBType
from app.core.logging import get_logger

logger = get_logger(__name__)

# ── tag patterns ──────────────────────────────────────────────────────────────
_CHURN_RE   = re.compile(r"(churn|churned|cancel|inactive|lost|unsubscrib)", re.I)
_REVENUE_RE = re.compile(r"(revenue|amount|value|sales|price|total|ltv|arr|mrr|gmv)", re.I)
_DATETIME_RE= re.compile(r"(created|updated|date|time|timestamp|at$|_date|_time)", re.I)
_ID_RE      = re.compile(r"(^id$|_id$|_uuid$|^uuid$|^pk$)", re.I)
_SCORE_RE   = re.compile(r"(score|rating|rank|probability|propensity)", re.I)


def _tag_column(col_name: str, dtype: str, cardinality: int, row_count: int) -> str:
    n, t = col_name.lower(), dtype.lower()
    if _ID_RE.search(n):                                          return "id"
    if _DATETIME_RE.search(n):                                    return "datetime"
    if _CHURN_RE.search(n):                                       return "target_churn"
    if _REVENUE_RE.search(n):                                     return "target_revenue"
    if _SCORE_RE.search(n):                                       return "target_score"
    if "bool" in t:                                               return "target_churn"
    if any(x in t for x in ["int","float","numeric","decimal"]):  return "numeric"
    ratio = cardinality / max(row_count, 1)
    if cardinality <= 20 and ratio < 0.05:                        return "categorical"
    return "text"


# ── data classes ──────────────────────────────────────────────────────────────

@dataclass
class ColumnProfile:
    name:          str
    dtype:         str
    null_pct:      float
    cardinality:   int
    sample_values: List[Any]
    tag:           str


@dataclass
class TableProfile:
    name:         str
    row_count:    int
    column_count: int
    columns:      List[ColumnProfile] = field(default_factory=list)


@dataclass
class SuggestedFeature:
    id:              str
    table:           str
    target_column:   str
    goal:            str
    title:           str
    description:     str
    feature_columns: List[str] = field(default_factory=list)
    row_count:       int       = 0
    confidence:      float     = 0.8


# ── main scanner ──────────────────────────────────────────────────────────────

class ETLScanner:

    def _build_url(self, conn: DBConnection) -> str:
        pw = decrypt_credential(conn.encrypted_password)
        if conn.db_type == DBType.postgres:
            return f"postgresql+psycopg2://{conn.username}:{pw}@{conn.host}:{conn.port}/{conn.database}"
        return f"mysql+pymysql://{conn.username}:{pw}@{conn.host}:{conn.port}/{conn.database}"

    # ── public entry ──────────────────────────────────────────────────────────

    def scan_and_suggest(self, conn: DBConnection) -> Dict[str, Any]:
        engine = create_engine(self._build_url(conn), pool_pre_ping=True)
        try:
            profiles    = self._profile_all_tables(engine)
            suggestions = self._generate_suggestions(profiles)
            return {
                "tables":      [self._profile_to_dict(p) for p in profiles],
                "suggestions": [asdict(s) for s in suggestions],
            }
        finally:
            engine.dispose()

    def fetch_table_as_dataframe(
        self,
        conn:    DBConnection,
        table:   str,
        limit:   int = 500_000,
    ) -> pd.DataFrame:
        """
        Load a table using Dask partitioned reads, then compute to pandas.
        Falls back to direct pandas read for small tables.
        """
        url    = self._build_url(conn)
        engine = create_engine(url, pool_pre_ping=True)
        try:
            row_count = self._fast_count(engine, table)

            if row_count > 50_000:
                # Use Dask for large tables — reads in parallel partitions
                logger.info("dask_read_start", table=table, rows=row_count)
                ddf = dd.read_sql_table(
                    table_name     = table,
                    con            = url,
                    index_col      = self._find_index_col(engine, table),
                    npartitions    = max(2, row_count // 100_000),
                )
                df = ddf.compute()
                logger.info("dask_read_done", table=table, shape=df.shape)
            else:
                with engine.connect() as c:
                    df = pd.read_sql(
                        text(f'SELECT * FROM "{table}" LIMIT :lim'),
                        c, params={"lim": limit}
                    )

            return df.head(limit) if len(df) > limit else df

        finally:
            engine.dispose()

    # ── profiling with Dask ───────────────────────────────────────────────────

    def _profile_all_tables(self, engine) -> List[TableProfile]:
        inspector = inspect(engine)
        profiles: List[TableProfile] = []
        for table_name in inspector.get_table_names():
            try:
                profiles.append(self._profile_table(engine, table_name, inspector))
            except Exception as exc:
                logger.warning("profile_failed", table=table_name, error=str(exc))
        return profiles

    def _profile_table(self, engine, table_name: str, inspector) -> TableProfile:
        row_count = self._fast_count(engine, table_name)
        url       = str(engine.url)

        if row_count > 20_000:
            # Dask path — lazy compute, one pass
            try:
                idx_col = self._find_index_col(engine, table_name)
                ddf = dd.read_sql_table(
                    table_name  = table_name,
                    con         = url,
                    index_col   = idx_col,
                    npartitions = max(2, row_count // 50_000),
                )

                # Build all aggregations lazily then compute in ONE shot
                agg_tasks = {}
                for col in ddf.columns:
                    agg_tasks[f"{col}__null"]  = ddf[col].isna().mean()
                    agg_tasks[f"{col}__nuniq"] = ddf[col].nunique()

                import dask
                computed = dask.compute(agg_tasks)[0]

                # Sample — just read first partition (cheap)
                sample_df = ddf.get_partition(0).compute().head(5)

            except Exception as exc:
                logger.warning("dask_profile_fallback", table=table_name, error=str(exc))
                # fallback to pandas sample
                with engine.connect() as c:
                    sample_df = pd.read_sql(
                        text(f'SELECT * FROM "{table_name}" LIMIT 500'), c
                    )
                computed = {
                    f"{col}__null":  float(sample_df[col].isna().mean())
                    for col in sample_df.columns
                } | {
                    f"{col}__nuniq": int(sample_df[col].nunique())
                    for col in sample_df.columns
                }
        else:
            # Small table — pandas is fine
            with engine.connect() as c:
                sample_df = pd.read_sql(
                    text(f'SELECT * FROM "{table_name}" LIMIT 500'), c
                )
            computed = {
                f"{col}__null":  float(sample_df[col].isna().mean())
                for col in sample_df.columns
            } | {
                f"{col}__nuniq": int(sample_df[col].nunique())
                for col in sample_df.columns
            }

        cols_meta = {c["name"]: c for c in inspector.get_columns(table_name)}
        col_profiles: List[ColumnProfile] = []

        for col in sample_df.columns:
            null_pct    = round(float(computed.get(f"{col}__null", 0) * 100), 1)
            cardinality = int(computed.get(f"{col}__nuniq", 0))
            dtype_str   = str(cols_meta.get(col, {}).get("type", sample_df[col].dtype))
            tag         = _tag_column(col, dtype_str, cardinality, row_count)

            raw_samples = sample_df[col].dropna().head(5).tolist()
            safe_samples = []
            for v in raw_samples:
                try:
                    json.dumps(v); safe_samples.append(v)
                except Exception:
                    safe_samples.append(str(v))

            col_profiles.append(ColumnProfile(
                name          = col,
                dtype         = dtype_str,
                null_pct      = null_pct,
                cardinality   = cardinality,
                sample_values = safe_samples,
                tag           = tag,
            ))

        return TableProfile(
            name         = table_name,
            row_count    = int(row_count),
            column_count = len(col_profiles),
            columns      = col_profiles,
        )

    # ── suggestion generation (unchanged logic) ───────────────────────────────

    def _generate_suggestions(self, profiles: List[TableProfile]) -> List[SuggestedFeature]:
        suggestions: List[SuggestedFeature] = []

        for table in profiles:
            if table.row_count < 50:
                continue

            col_by_tag: Dict[str, List[str]] = {}
            for col in table.columns:
                col_by_tag.setdefault(col.tag, []).append(col.name)

            feature_cols = [
                c.name for c in table.columns
                if c.tag not in ("id","target_churn","target_revenue",
                                  "target_score","datetime","text")
                and c.null_pct < 60
            ]

            for target_col in col_by_tag.get("target_churn", []):
                suggestions.append(SuggestedFeature(
                    id            = f"{table.name}__{target_col}__churn",
                    table         = table.name,
                    target_column = target_col,
                    goal          = "churn",
                    title         = f"Predict churn — {table.name}",
                    description   = (
                        f"Use {len(feature_cols)} features from '{table.name}' "
                        f"to predict '{target_col}'. {table.row_count:,} rows."
                    ),
                    feature_columns = feature_cols,
                    row_count     = table.row_count,
                    confidence    = 0.95,
                ))

            for target_col in col_by_tag.get("target_revenue", []):
                suggestions.append(SuggestedFeature(
                    id            = f"{table.name}__{target_col}__revenue",
                    table         = table.name,
                    target_column = target_col,
                    goal          = "revenue_forecast",
                    title         = f"Forecast revenue — {table.name}",
                    description   = (
                        f"Predict '{target_col}' from {len(feature_cols)} features. "
                        f"{table.row_count:,} rows."
                    ),
                    feature_columns = feature_cols,
                    row_count     = table.row_count,
                    confidence    = 0.90,
                ))

            for col in table.columns:
                if col.tag in ("target_churn","target_revenue"):
                    continue
                if ("bool" in col.dtype.lower() or
                    (col.cardinality <= 5 and col.cardinality >= 2
                     and col.tag == "categorical")):
                    suggestions.append(SuggestedFeature(
                        id            = f"{table.name}__{col.name}__classification",
                        table         = table.name,
                        target_column = col.name,
                        goal          = "classification",
                        title         = f"Classify {col.name} — {table.name}",
                        description   = (
                            f"Predict '{col.name}' ({col.cardinality} classes). "
                            f"{table.row_count:,} rows."
                        ),
                        feature_columns = [c for c in feature_cols if c != col.name],
                        row_count     = table.row_count,
                        confidence    = 0.75,
                    ))

        seen: Dict[str, SuggestedFeature] = {}
        for s in suggestions:
            if s.id not in seen or s.confidence > seen[s.id].confidence:
                seen[s.id] = s

        return sorted(seen.values(), key=lambda x: -x.confidence)

    # ── helpers ───────────────────────────────────────────────────────────────

    def _fast_count(self, engine, table_name: str) -> int:
        try:
            with engine.connect() as c:
                return int(
                    c.execute(text(f'SELECT COUNT(*) FROM "{table_name}"')).scalar() or 0
                )
        except Exception:
            return 0

    def _find_index_col(self, engine, table_name: str) -> str:
        """
        Dask's read_sql_table requires an index column for partitioning.
        Prefer integer primary key; fall back to first column.
        """
        try:
            inspector = inspect(engine)
            pk = inspector.get_pk_constraint(table_name).get("constrained_columns", [])
            if pk:
                return pk[0]
            cols = inspector.get_columns(table_name)
            for col in cols:
                t = str(col["type"]).lower()
                if any(x in t for x in ["int","serial","bigint"]):
                    return col["name"]
            return cols[0]["name"]
        except Exception:
            return "id"

    @staticmethod
    def _profile_to_dict(p: TableProfile) -> dict:
        return {
            "name":         p.name,
            "row_count":    p.row_count,
            "column_count": p.column_count,
            "columns": [
                {
                    "name":          c.name,
                    "dtype":         c.dtype,
                    "null_pct":      c.null_pct,
                    "cardinality":   c.cardinality,
                    "sample_values": c.sample_values,
                    "tag":           c.tag,
                }
                for c in p.columns
            ],
        }


etl_scanner = ETLScanner()
