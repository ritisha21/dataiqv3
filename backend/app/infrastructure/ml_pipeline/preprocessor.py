"""
backend/app/infrastructure/ml_pipeline/preprocessor.py
───────────────────────────────────────────────────────
Data preprocessing pipeline that runs BEFORE feature engineering.
Handles:
  1. Bad row detection — flags rows that won't meet training expectations
  2. Missing value strategy — smart imputation per column type
  3. Outlier detection — IQR-based flagging and capping
  4. Target validation — ensures target is trainable
  5. Data quality report — returned alongside the cleaned DataFrame
"""

from __future__ import annotations

from typing import Dict, List, Tuple, Any, Optional

import numpy as np
import pandas as pd

from app.core.logging import get_logger

logger = get_logger(__name__)


# ─── Thresholds ───────────────────────────────────────────────────────────────

NULL_DROP_THRESHOLD    = 0.95   # drop column if >95% null
NULL_IMPUTE_THRESHOLD  = 0.50   # impute if 50-95% null (warn), else impute silently
ROW_NULL_THRESHOLD     = 0.70   # drop row if >70% of its values are null
OUTLIER_IQR_FACTOR     = 3.0    # cap outliers at median ± 3*IQR
MIN_ROWS_AFTER_CLEAN   = 30     # raise if fewer rows remain


# ─── Data quality report ──────────────────────────────────────────────────────

class DataQualityReport:
    def __init__(self):
        self.original_shape: Tuple[int, int] = (0, 0)
        self.final_shape: Tuple[int, int]    = (0, 0)
        self.dropped_columns: List[str]      = []
        self.dropped_rows: int               = 0
        self.imputed_columns: List[Dict]     = []
        self.capped_columns: List[str]       = []
        self.target_issues: List[str]        = []
        self.warnings: List[str]             = []
        self.passed: bool                    = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "original_rows":    self.original_shape[0],
            "original_cols":    self.original_shape[1],
            "final_rows":       self.final_shape[0],
            "final_cols":       self.final_shape[1],
            "rows_dropped":     self.dropped_rows,
            "cols_dropped":     len(self.dropped_columns),
            "dropped_columns":  self.dropped_columns,
            "imputed_columns":  self.imputed_columns,
            "capped_columns":   self.capped_columns,
            "target_issues":    self.target_issues,
            "warnings":         self.warnings,
            "passed":           self.passed,
            "data_quality_pct": round(
                self.final_shape[0] / max(self.original_shape[0], 1) * 100, 1
            ),
        }


# ─── Main preprocessor ────────────────────────────────────────────────────────

def preprocess(
    df: pd.DataFrame,
    target_col: str,
    drop_high_null_cols: bool = True,
    impute_strategy: str = "median",   # "median" | "mean" | "mode" | "zero"
    cap_outliers: bool = True,
    drop_duplicates: bool = True,
) -> Tuple[pd.DataFrame, DataQualityReport]:
    """
    Full preprocessing pipeline. Returns (clean_df, report).
    """
    report = DataQualityReport()
    df = df.copy()
    report.original_shape = df.shape

    # ── 1. Drop duplicate rows ────────────────────────────────────────────────
    if drop_duplicates:
        before = len(df)
        df = df.drop_duplicates()
        removed = before - len(df)
        if removed > 0:
            report.warnings.append(f"Dropped {removed} duplicate rows.")

    # ── 2. Validate target column ─────────────────────────────────────────────
    if target_col not in df.columns:
        report.target_issues.append(f"Target column '{target_col}' not found.")
        report.passed = False
        report.final_shape = df.shape
        return df, report

    target_null_pct = df[target_col].isnull().mean()
    if target_null_pct > 0.5:
        report.target_issues.append(
            f"Target '{target_col}' is {target_null_pct:.0%} null — too many missing values."
        )
        report.warnings.append("Dropping rows with null target.")

    # Drop rows with null target
    before = len(df)
    df = df.dropna(subset=[target_col])
    report.dropped_rows += before - len(df)

    if len(df) < MIN_ROWS_AFTER_CLEAN:
        report.target_issues.append(
            f"Only {len(df)} rows remain after removing null targets. "
            f"Need at least {MIN_ROWS_AFTER_CLEAN}."
        )
        report.passed = False
        report.final_shape = df.shape
        return df, report

    # Check target variance
    target_numeric = pd.to_numeric(df[target_col], errors="coerce")
    if target_numeric.notna().sum() > 0:
        if target_numeric.nunique() < 2:
            report.target_issues.append(
                f"Target '{target_col}' has only 1 unique value — cannot train."
            )
            report.passed = False

    # ── 3. Drop rows that are mostly null ─────────────────────────────────────
    row_null_rates = df.isnull().mean(axis=1)
    bad_rows = row_null_rates > ROW_NULL_THRESHOLD
    if bad_rows.sum() > 0:
        report.dropped_rows += bad_rows.sum()
        report.warnings.append(
            f"Dropped {bad_rows.sum()} rows where >{ROW_NULL_THRESHOLD:.0%} of values were null."
        )
        df = df[~bad_rows]

    # ── 4. Drop high-null columns ─────────────────────────────────────────────
    if drop_high_null_cols:
        col_null_rates = df.isnull().mean()
        high_null = col_null_rates[
            (col_null_rates > NULL_DROP_THRESHOLD) & (col_null_rates.index != target_col)
        ].index.tolist()
        if high_null:
            report.dropped_columns.extend(high_null)
            report.warnings.append(
                f"Dropped {len(high_null)} columns with >{NULL_DROP_THRESHOLD:.0%} null: "
                f"{', '.join(high_null[:5])}{'...' if len(high_null) > 5 else ''}"
            )
            df = df.drop(columns=high_null)

        # Warn about moderately-null columns
        moderate_null = col_null_rates[
            (col_null_rates > NULL_IMPUTE_THRESHOLD) &
            (col_null_rates <= NULL_DROP_THRESHOLD) &
            (col_null_rates.index != target_col)
        ].index.tolist()
        for col in moderate_null:
            report.warnings.append(
                f"Column '{col}' is {col_null_rates[col]:.0%} null — imputing."
            )

    # ── 5. Impute missing values ──────────────────────────────────────────────
    feature_cols = [c for c in df.columns if c != target_col]
    num_cols = df[feature_cols].select_dtypes(include=[np.number]).columns.tolist()
    cat_cols = df[feature_cols].select_dtypes(include=["object"]).columns.tolist()

    for col in num_cols:
        null_count = df[col].isnull().sum()
        if null_count == 0:
            continue

        if impute_strategy == "mean":
            fill_val = df[col].mean()
        elif impute_strategy == "mode":
            fill_val = df[col].mode().iloc[0] if not df[col].mode().empty else 0
        elif impute_strategy == "zero":
            fill_val = 0
        else:  # median (default)
            fill_val = df[col].median()

        df[col] = df[col].fillna(fill_val)
        report.imputed_columns.append({
            "col": col, "strategy": impute_strategy,
            "fill_value": round(float(fill_val), 4), "n_filled": int(null_count)
        })

    for col in cat_cols:
        null_count = df[col].isnull().sum()
        if null_count == 0:
            continue
        mode_val = df[col].mode().iloc[0] if not df[col].mode().empty else "unknown"
        df[col] = df[col].fillna(mode_val)
        report.imputed_columns.append({
            "col": col, "strategy": "mode",
            "fill_value": str(mode_val), "n_filled": int(null_count)
        })

    # ── 6. Cap outliers in numeric columns ───────────────────────────────────
    if cap_outliers:
        for col in num_cols:
            if col not in df.columns:
                continue
            q1 = df[col].quantile(0.25)
            q3 = df[col].quantile(0.75)
            iqr = q3 - q1
            if iqr == 0:
                continue
            lower = q1 - OUTLIER_IQR_FACTOR * iqr
            upper = q3 + OUTLIER_IQR_FACTOR * iqr
            outlier_count = ((df[col] < lower) | (df[col] > upper)).sum()
            if outlier_count > 0:
                df[col] = df[col].clip(lower=lower, upper=upper)
                report.capped_columns.append(col)

    # ── 7. Remove constant columns ────────────────────────────────────────────
    constant_cols = [
        c for c in df.columns
        if c != target_col and df[c].nunique() <= 1
    ]
    if constant_cols:
        df = df.drop(columns=constant_cols)
        report.dropped_columns.extend(constant_cols)
        report.warnings.append(
            f"Dropped {len(constant_cols)} constant columns: {constant_cols[:5]}"
        )

    report.final_shape = df.shape
    report.dropped_rows = report.original_shape[0] - df.shape[0]

    logger.info(
        "preprocessing_complete",
        original=report.original_shape,
        final=report.final_shape,
        rows_dropped=report.dropped_rows,
        cols_dropped=len(report.dropped_columns),
        passed=report.passed,
    )

    return df, report


def validate_for_training(report: DataQualityReport) -> None:
    """Raises ValueError if the data quality report indicates training should not proceed."""
    if not report.passed:
        issues = "; ".join(report.target_issues)
        raise ValueError(f"Data quality check failed: {issues}")
    if report.final_shape[0] < MIN_ROWS_AFTER_CLEAN:
        raise ValueError(
            f"Insufficient data after preprocessing: {report.final_shape[0]} rows "
            f"(need at least {MIN_ROWS_AFTER_CLEAN})"
        )