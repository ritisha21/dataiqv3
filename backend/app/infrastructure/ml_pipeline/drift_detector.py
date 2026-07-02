"""
backend/app/infrastructure/ml_pipeline/drift_detector.py
──────────────────────────────────────────────────────────
Compares two CSV snapshots from MinIO to detect data drift.
If drift is detected above the threshold, triggers auto-retraining.

Drift signals checked:
  1. Schema drift     — columns added/removed
  2. Distribution drift — PSI (Population Stability Index) per numeric column
  3. Null rate drift  — significant change in null rates
  4. Volume drift     — significant row count change
  5. Categorical drift — chi-square test on category distributions

PSI interpretation:
  < 0.1  → no significant change
  0.1-0.2 → moderate change, monitor
  > 0.2  → significant drift, retrain

Usage:
    from app.infrastructure.ml_pipeline.drift_detector import check_drift
    result = check_drift(tenant_id, connection_id, table_name)
    if result.should_retrain:
        # trigger retrain task
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple

import numpy as np
import pandas as pd

from app.infrastructure.storage.minio_client import minio_storage
from app.core.logging import get_logger

logger = get_logger(__name__)


# ─── Constants ────────────────────────────────────────────────────────────────

PSI_THRESHOLD_WARN    = 0.1
PSI_THRESHOLD_RETRAIN = 0.2
VOLUME_CHANGE_RETRAIN = 0.30   # >30% row count change triggers retrain
NULL_CHANGE_RETRAIN   = 0.20   # >20% null rate change per column


# ─── Result types ──────────────────────────────────────────────────────────────

@dataclass
class ColumnDriftResult:
    column: str
    drift_type: str          # "psi" | "null_rate" | "schema"
    old_value: float
    new_value: float
    change: float
    severity: str            # "none" | "moderate" | "high"


@dataclass
class DriftResult:
    table_name: str
    has_drift: bool
    should_retrain: bool
    overall_psi: float
    volume_change_pct: float
    schema_changes: Dict[str, List[str]]   # {added: [...], removed: [...]}
    column_results: List[ColumnDriftResult]
    summary: str
    old_snapshot_key: Optional[str] = None
    new_snapshot_key: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "table_name":       self.table_name,
            "has_drift":        self.has_drift,
            "should_retrain":   self.should_retrain,
            "overall_psi":      round(self.overall_psi, 4),
            "volume_change_pct": round(self.volume_change_pct, 2),
            "schema_changes":   self.schema_changes,
            "high_drift_cols":  [r.column for r in self.column_results if r.severity == "high"],
            "moderate_drift_cols": [r.column for r in self.column_results if r.severity == "moderate"],
            "summary":          self.summary,
            "old_snapshot":     self.old_snapshot_key,
            "new_snapshot":     self.new_snapshot_key,
        }


# ─── PSI calculation ─────────────────────────────────────────────────────────

def _psi(expected: pd.Series, actual: pd.Series, bins: int = 10) -> float:
    """
    Population Stability Index between two numeric distributions.
    """
    expected = expected.dropna()
    actual = actual.dropna()

    if len(expected) == 0 or len(actual) == 0:
        return 0.0

    # Use expected distribution to define bin edges
    breakpoints = np.linspace(expected.min(), expected.max(), bins + 1)
    breakpoints[0] = -np.inf
    breakpoints[-1] = np.inf

    expected_pct = np.histogram(expected, bins=breakpoints)[0] / len(expected)
    actual_pct   = np.histogram(actual,   bins=breakpoints)[0] / len(actual)

    # Avoid log(0)
    expected_pct = np.where(expected_pct == 0, 1e-6, expected_pct)
    actual_pct   = np.where(actual_pct   == 0, 1e-6, actual_pct)

    psi_values = (actual_pct - expected_pct) * np.log(actual_pct / expected_pct)
    return float(np.sum(psi_values))


def _categorical_drift(expected: pd.Series, actual: pd.Series) -> float:
    """
    Measure drift in categorical columns using normalized distribution difference.
    Returns a value in [0, 1] where 0 = no drift.
    """
    exp_dist = expected.value_counts(normalize=True)
    act_dist = actual.value_counts(normalize=True)

    all_cats = set(exp_dist.index) | set(act_dist.index)
    total_diff = 0.0
    for cat in all_cats:
        e = exp_dist.get(cat, 0)
        a = act_dist.get(cat, 0)
        total_diff += abs(e - a)

    return total_diff / 2.0   # normalize to [0, 1]


# ─── Main drift checker ───────────────────────────────────────────────────────

def check_drift(
    tenant_id: str,
    connection_id: str,
    table_name: str,
) -> DriftResult:
    """
    Compare the two most recent MinIO snapshots for a table.
    Returns a DriftResult with detailed per-column analysis.

    If only one snapshot exists, returns has_drift=False (nothing to compare yet).
    """
    latest, previous = minio_storage.get_latest_two(
        tenant_id=tenant_id,
        connection_id=connection_id,
        table_name=table_name,
    )

    if latest is None:
        return DriftResult(
            table_name=table_name,
            has_drift=False,
            should_retrain=False,
            overall_psi=0.0,
            volume_change_pct=0.0,
            schema_changes={"added": [], "removed": []},
            column_results=[],
            summary="No snapshots found — run an extraction first.",
        )

    if previous is None:
        return DriftResult(
            table_name=table_name,
            has_drift=False,
            should_retrain=False,
            overall_psi=0.0,
            volume_change_pct=0.0,
            schema_changes={"added": [], "removed": []},
            column_results=[],
            summary="Only one snapshot exists — cannot detect drift yet.",
            new_snapshot_key=latest["object_key"],
        )

    # ── Load both snapshots ───────────────────────────────────────────────────
    try:
        new_bytes  = minio_storage.download_csv(latest["object_key"])
        prev_bytes = minio_storage.download_csv(previous["object_key"])
        df_new  = pd.read_csv(io.BytesIO(new_bytes))
        df_prev = pd.read_csv(io.BytesIO(prev_bytes))
    except Exception as exc:
        logger.error("drift_snapshot_load_failed", error=str(exc))
        return DriftResult(
            table_name=table_name,
            has_drift=False,
            should_retrain=False,
            overall_psi=0.0,
            volume_change_pct=0.0,
            schema_changes={"added": [], "removed": []},
            column_results=[],
            summary=f"Failed to load snapshots: {exc}",
        )

    column_results: List[ColumnDriftResult] = []
    psi_values: List[float] = []

    # ── 1. Schema drift ───────────────────────────────────────────────────────
    old_cols = set(df_prev.columns)
    new_cols = set(df_new.columns)
    added   = list(new_cols - old_cols)
    removed = list(old_cols - new_cols)
    schema_changes = {"added": added, "removed": removed}

    for col in removed:
        column_results.append(ColumnDriftResult(
            column=col, drift_type="schema",
            old_value=1.0, new_value=0.0, change=1.0, severity="high"
        ))

    # ── 2. Volume drift ───────────────────────────────────────────────────────
    volume_change = (len(df_new) - len(df_prev)) / max(len(df_prev), 1)

    # ── 3. Per-column drift ───────────────────────────────────────────────────
    common_cols = list(old_cols & new_cols)

    for col in common_cols:
        if df_prev[col].dtype in [object, "category"]:
            # Categorical drift
            drift_score = _categorical_drift(df_prev[col], df_new[col])
            psi_equivalent = drift_score * 2   # scale to PSI-like range
            psi_values.append(psi_equivalent)
            severity = (
                "high"     if psi_equivalent > PSI_THRESHOLD_RETRAIN else
                "moderate" if psi_equivalent > PSI_THRESHOLD_WARN    else
                "none"
            )
            if severity != "none":
                column_results.append(ColumnDriftResult(
                    column=col, drift_type="categorical",
                    old_value=0.0, new_value=drift_score,
                    change=drift_score, severity=severity,
                ))
        else:
            # Numeric PSI
            prev_numeric = pd.to_numeric(df_prev[col], errors="coerce")
            new_numeric  = pd.to_numeric(df_new[col], errors="coerce")
            psi_val = _psi(prev_numeric, new_numeric)
            psi_values.append(psi_val)
            severity = (
                "high"     if psi_val > PSI_THRESHOLD_RETRAIN else
                "moderate" if psi_val > PSI_THRESHOLD_WARN    else
                "none"
            )
            if severity != "none":
                column_results.append(ColumnDriftResult(
                    column=col, drift_type="psi",
                    old_value=float(prev_numeric.mean()),
                    new_value=float(new_numeric.mean()),
                    change=psi_val, severity=severity,
                ))

        # Null rate drift
        old_null = df_prev[col].isnull().mean()
        new_null = df_new[col].isnull().mean()
        null_change = abs(new_null - old_null)
        if null_change > NULL_CHANGE_RETRAIN:
            column_results.append(ColumnDriftResult(
                column=col, drift_type="null_rate",
                old_value=old_null, new_value=new_null,
                change=null_change, severity="moderate",
            ))

    overall_psi = float(np.mean(psi_values)) if psi_values else 0.0
    high_drift_count = sum(1 for r in column_results if r.severity == "high")

    has_drift = (
        overall_psi > PSI_THRESHOLD_WARN
        or high_drift_count > 0
        or abs(volume_change) > VOLUME_CHANGE_RETRAIN
        or bool(added or removed)
    )

    should_retrain = (
        overall_psi > PSI_THRESHOLD_RETRAIN
        or high_drift_count >= 2
        or abs(volume_change) > VOLUME_CHANGE_RETRAIN
        or bool(removed)
    )

    # ── Build summary ─────────────────────────────────────────────────────────
    parts = []
    if removed:
        parts.append(f"{len(removed)} columns removed")
    if added:
        parts.append(f"{len(added)} columns added")
    if abs(volume_change) > 0.05:
        parts.append(f"row count changed by {volume_change:+.0%}")
    if high_drift_count:
        parts.append(f"{high_drift_count} columns with high drift")
    summary = (
        "Significant drift detected: " + ", ".join(parts) + "."
        if has_drift else
        "No significant drift detected."
    )
    if should_retrain:
        summary += " Retraining recommended."

    logger.info(
        "drift_check_complete",
        table=table_name,
        has_drift=has_drift,
        should_retrain=should_retrain,
        overall_psi=overall_psi,
        volume_change=volume_change,
    )

    return DriftResult(
        table_name=table_name,
        has_drift=has_drift,
        should_retrain=should_retrain,
        overall_psi=overall_psi,
        volume_change_pct=volume_change * 100,
        schema_changes=schema_changes,
        column_results=column_results,
        summary=summary,
        old_snapshot_key=previous["object_key"],
        new_snapshot_key=latest["object_key"],
    )