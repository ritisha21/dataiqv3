"""
feature_engineering.py
───────────────────────
Proper feature engineering per CRM model type.
Each model type gets its own FeatureBuilder with:
  - Domain-specific computed features (RFM, tenure bands, etc.)
  - Null-safe calculations
  - Returns a DataFrame ready for model training

Usage:
    from feature_engineering import build_features

    X, y, meta = build_features(df, model_type="churn_prediction")
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Tuple, Dict, Any, List, Optional

# ── safe import for pandas (installed in your env) ──────────────────────────
try:
    import pandas as pd
    import numpy as np
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False

REFERENCE_DATE = datetime.now(timezone.utc)


# ─────────────────────────────────────────────────────────────────────────────
# Column auto-detection helpers
# ─────────────────────────────────────────────────────────────────────────────

def _find_col(df: "pd.DataFrame", candidates: List[str]) -> Optional[str]:
    """Return first matching column name (case-insensitive) or None."""
    lower_cols = {c.lower(): c for c in df.columns}
    for cand in candidates:
        if cand.lower() in lower_cols:
            return lower_cols[cand.lower()]
    return None


def _days_since(df: "pd.DataFrame", col: str) -> "pd.Series":
    """Return days since a datetime column, clamped to [0, 3650]."""
    dates = pd.to_datetime(df[col], errors="coerce", utc=True)
    now = pd.Timestamp.now(tz="UTC")
    delta = (now - dates).dt.days.fillna(3650).clip(0, 3650)
    return delta


# ─────────────────────────────────────────────────────────────────────────────
# 1. CHURN PREDICTION — RFM + tenure
# ─────────────────────────────────────────────────────────────────────────────

def _build_churn_features(df: "pd.DataFrame") -> Tuple["pd.DataFrame", Dict]:
    """
    Features:
      recency        – days since last order/contact
      frequency      – number of orders/interactions
      monetary       – total spend
      tenure_days    – days since account creation
      avg_order_val  – monetary / max(frequency, 1)
      days_inactive  – days with no interaction
      support_count  – number of support tickets
      rfm_score      – composite 1-5 score per dimension
    """
    feats: Dict[str, Any] = {}
    meta: Dict[str, Any] = {"model": "churn_prediction", "features_used": []}

    # Recency
    recency_col = _find_col(df, ["last_order_date", "last_purchase_date",
                                  "last_contact_date", "updated_at"])
    if recency_col:
        feats["recency"] = _days_since(df, recency_col)
        meta["features_used"].append("recency")
    else:
        feats["recency"] = 365  # pessimistic default

    # Frequency
    freq_col = _find_col(df, ["order_count", "purchase_count",
                               "interaction_count", "num_orders", "total_orders"])
    if freq_col:
        feats["frequency"] = pd.to_numeric(df[freq_col], errors="coerce").fillna(0)
        meta["features_used"].append("frequency")
    else:
        feats["frequency"] = 1

    # Monetary
    monetary_col = _find_col(df, ["total_spend", "total_revenue",
                                   "lifetime_value", "total_amount", "ltv"])
    if monetary_col:
        feats["monetary"] = pd.to_numeric(df[monetary_col], errors="coerce").fillna(0)
        meta["features_used"].append("monetary")
    else:
        feats["monetary"] = 0

    # Tenure
    tenure_col = _find_col(df, ["created_at", "signup_date",
                                 "registration_date", "account_created"])
    if tenure_col:
        feats["tenure_days"] = _days_since(df, tenure_col)
        meta["features_used"].append("tenure_days")
    else:
        feats["tenure_days"] = 180

    # Derived
    freq = feats["frequency"] if isinstance(feats["frequency"], pd.Series) else pd.Series([feats["frequency"]] * len(df))
    mon = feats["monetary"] if isinstance(feats["monetary"], pd.Series) else pd.Series([feats["monetary"]] * len(df))
    feats["avg_order_value"] = mon / freq.clip(lower=1)

    # Support tickets (negative signal)
    support_col = _find_col(df, ["support_tickets", "ticket_count",
                                  "complaint_count", "case_count"])
    if support_col:
        feats["support_count"] = pd.to_numeric(df[support_col], errors="coerce").fillna(0)
        meta["features_used"].append("support_count")

    # RFM quintile scores (1=worst, 5=best)
    result = pd.DataFrame(feats)
    for col, ascending in [("recency", True), ("frequency", False), ("monetary", False)]:
        if col in result.columns and result[col].nunique() > 1:
            try:
                result[f"{col}_score"] = pd.qcut(
                    result[col], q=5, labels=[5, 4, 3, 2, 1] if ascending else [1, 2, 3, 4, 5],
                    duplicates="drop"
                ).astype(float)
            except Exception:
                result[f"{col}_score"] = 3.0

    return result, meta


# ─────────────────────────────────────────────────────────────────────────────
# 2. CLV PREDICTION — spend trajectory + frequency bands
# ─────────────────────────────────────────────────────────────────────────────

def _build_clv_features(df: "pd.DataFrame") -> Tuple["pd.DataFrame", Dict]:
    """
    Features:
      avg_order_value       – mean spend per order
      purchase_frequency    – orders per month
      tenure_months         – how long they've been a customer
      predicted_lifespan    – estimated months remaining (heuristic)
      gross_margin_proxy    – AOV * 0.3 as margin estimate if not available
      monthly_revenue_rate  – AOV × frequency
    """
    feats: Dict[str, Any] = {}
    meta: Dict[str, Any] = {"model": "clv_prediction", "features_used": []}

    # AOV
    aov_col = _find_col(df, ["avg_order_value", "average_order_value",
                              "aov", "mean_spend"])
    if aov_col:
        feats["avg_order_value"] = pd.to_numeric(df[aov_col], errors="coerce").fillna(0)
        meta["features_used"].append("avg_order_value")
    else:
        # compute from total / count
        total_col = _find_col(df, ["total_spend", "total_revenue", "total_amount"])
        count_col = _find_col(df, ["order_count", "num_orders", "purchase_count"])
        if total_col and count_col:
            total = pd.to_numeric(df[total_col], errors="coerce").fillna(0)
            count = pd.to_numeric(df[count_col], errors="coerce").fillna(1).clip(lower=1)
            feats["avg_order_value"] = total / count
        else:
            feats["avg_order_value"] = 50.0  # fallback

    # Frequency per month
    freq_col = _find_col(df, ["order_count", "num_orders", "purchase_count"])
    tenure_col = _find_col(df, ["created_at", "signup_date", "account_created"])
    if freq_col and tenure_col:
        freq = pd.to_numeric(df[freq_col], errors="coerce").fillna(1)
        tenure_months = _days_since(df, tenure_col) / 30.0
        tenure_months = tenure_months.clip(lower=1)
        feats["purchase_frequency"] = freq / tenure_months
        feats["tenure_months"] = tenure_months
        meta["features_used"] += ["purchase_frequency", "tenure_months"]
    else:
        feats["purchase_frequency"] = 1.0
        feats["tenure_months"] = 6.0

    # Predicted lifespan heuristic: longer tenure → longer expected life (log scale)
    tm = feats["tenure_months"] if isinstance(feats["tenure_months"], pd.Series) else pd.Series([feats["tenure_months"]] * len(df))
    feats["predicted_lifespan_months"] = np.log1p(tm) * 6

    # Gross margin proxy
    margin_col = _find_col(df, ["gross_margin", "margin", "profit_margin"])
    if margin_col:
        feats["gross_margin_proxy"] = pd.to_numeric(df[margin_col], errors="coerce").fillna(0.3)
        meta["features_used"].append("gross_margin_proxy")
    else:
        aov = feats["avg_order_value"] if isinstance(feats["avg_order_value"], pd.Series) else pd.Series([feats["avg_order_value"]] * len(df))
        feats["gross_margin_proxy"] = aov * 0.3

    # Monthly revenue rate
    aov_s = feats["avg_order_value"] if isinstance(feats["avg_order_value"], pd.Series) else pd.Series([feats["avg_order_value"]] * len(df))
    freq_s = feats["purchase_frequency"] if isinstance(feats["purchase_frequency"], pd.Series) else pd.Series([feats["purchase_frequency"]] * len(df))
    feats["monthly_revenue_rate"] = aov_s * freq_s

    return pd.DataFrame(feats), meta


# ─────────────────────────────────────────────────────────────────────────────
# 3. LEAD SCORING — engagement + source + firmographic signals
# ─────────────────────────────────────────────────────────────────────────────

def _build_lead_score_features(df: "pd.DataFrame") -> Tuple["pd.DataFrame", Dict]:
    """
    Features:
      days_since_created     – lead age
      days_since_last_touch  – time since last engagement
      touchpoint_count       – total interactions
      email_opens            – email engagement
      page_views             – web engagement
      source_score           – ordinal encoding of acquisition source quality
      has_phone              – boolean
      has_company            – boolean
      stage_score            – ordinal pipeline stage
    """
    feats: Dict[str, Any] = {}
    meta: Dict[str, Any] = {"model": "lead_scoring", "features_used": []}

    created_col = _find_col(df, ["created_at", "lead_created", "signup_date"])
    if created_col:
        feats["days_since_created"] = _days_since(df, created_col)
        meta["features_used"].append("days_since_created")

    last_touch_col = _find_col(df, ["last_activity_date", "last_contact_date",
                                     "last_touch", "updated_at"])
    if last_touch_col:
        feats["days_since_last_touch"] = _days_since(df, last_touch_col)
        meta["features_used"].append("days_since_last_touch")

    touchpoint_col = _find_col(df, ["activity_count", "interaction_count",
                                     "touchpoint_count", "num_activities"])
    if touchpoint_col:
        feats["touchpoint_count"] = pd.to_numeric(df[touchpoint_col], errors="coerce").fillna(0)
        meta["features_used"].append("touchpoint_count")

    email_col = _find_col(df, ["email_opens", "emails_opened", "open_count"])
    if email_col:
        feats["email_opens"] = pd.to_numeric(df[email_col], errors="coerce").fillna(0)
        meta["features_used"].append("email_opens")

    pv_col = _find_col(df, ["page_views", "website_visits", "sessions"])
    if pv_col:
        feats["page_views"] = pd.to_numeric(df[pv_col], errors="coerce").fillna(0)
        meta["features_used"].append("page_views")

    # Source quality encoding
    SOURCE_QUALITY = {
        "organic": 5, "seo": 5, "referral": 4, "partner": 4,
        "email": 3, "paid": 3, "social": 2, "direct": 2, "unknown": 1, "": 1,
    }
    source_col = _find_col(df, ["lead_source", "acquisition_source",
                                 "utm_source", "source"])
    if source_col:
        feats["source_score"] = (
            df[source_col].fillna("").str.lower()
            .map(lambda s: max((v for k, v in SOURCE_QUALITY.items() if k in s), default=1))
        )
        meta["features_used"].append("source_score")

    # Boolean presence signals
    phone_col = _find_col(df, ["phone", "mobile", "phone_number"])
    if phone_col:
        feats["has_phone"] = df[phone_col].notna().astype(int)

    company_col = _find_col(df, ["company", "company_name", "organization"])
    if company_col:
        feats["has_company"] = df[company_col].notna().astype(int)

    # Stage ordinal
    STAGE_ORDER = {
        "new": 1, "contacted": 2, "qualified": 3, "proposal": 4,
        "negotiation": 5, "closed_won": 6, "closed_lost": 0,
    }
    stage_col = _find_col(df, ["stage", "pipeline_stage", "lead_stage", "status"])
    if stage_col:
        feats["stage_score"] = (
            df[stage_col].fillna("new").str.lower()
            .map(lambda s: next((v for k, v in STAGE_ORDER.items() if k in s), 1))
        )
        meta["features_used"].append("stage_score")

    return pd.DataFrame(feats), meta


# ─────────────────────────────────────────────────────────────────────────────
# Target column auto-detection
# ─────────────────────────────────────────────────────────────────────────────

TARGET_HINTS = {
    "churn_prediction": ["churned", "is_churned", "churn", "cancelled", "inactive"],
    "clv_prediction":   ["clv", "ltv", "lifetime_value", "total_revenue"],
    "lead_scoring":     ["converted", "is_converted", "won", "qualified"],
    "upsell_propensity": ["upgraded", "upsold", "plan_changed", "expansion"],
    "nps_prediction":   ["nps_score", "nps", "csat_score", "rating"],
}


def _find_target(df: "pd.DataFrame", model_type: str) -> Optional[str]:
    hints = TARGET_HINTS.get(model_type, [])
    lower_cols = {c.lower(): c for c in df.columns}
    for hint in hints:
        if hint.lower() in lower_cols:
            return lower_cols[hint.lower()]
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

FEATURE_BUILDERS = {
    "churn_prediction": _build_churn_features,
    "clv_prediction":   _build_clv_features,
    "lead_scoring":     _build_lead_score_features,
}


def build_features(
    df: "pd.DataFrame",
    model_type: str,
) -> Tuple["pd.DataFrame", Optional["pd.Series"], Dict[str, Any]]:
    """
    Build features for a given model type.

    Parameters
    ----------
    df         : Raw pandas DataFrame from the connected database.
    model_type : One of the keys in FEATURE_BUILDERS.

    Returns
    -------
    X    : Feature DataFrame (all numeric, no NaNs)
    y    : Target Series if a target column was found, else None
    meta : Dict with model_type, features_used, target_col, warnings
    """
    if not HAS_PANDAS:
        raise ImportError("pandas and numpy are required: pip install pandas numpy")

    if model_type not in FEATURE_BUILDERS:
        raise ValueError(
            f"Unknown model_type {model_type!r}. "
            f"Valid options: {list(FEATURE_BUILDERS)}"
        )

    builder = FEATURE_BUILDERS[model_type]
    X, meta = builder(df)

    # Enforce all-numeric, fill remaining NaNs
    X = X.apply(pd.to_numeric, errors="coerce").fillna(0)

    # Target detection
    target_col = _find_target(df, model_type)
    y: Optional["pd.Series"] = None
    if target_col:
        y = pd.to_numeric(df[target_col], errors="coerce").fillna(0)
        meta["target_col"] = target_col
    else:
        meta["warnings"] = meta.get("warnings", [])
        meta["warnings"].append(
            f"No target column found for {model_type}. "
            f"Expected one of: {TARGET_HINTS.get(model_type, [])}"
        )
        meta["target_col"] = None

    meta["n_samples"] = len(X)
    meta["n_features"] = len(X.columns)
    meta["feature_names"] = list(X.columns)

    return X, y, meta


def get_feature_summary(model_type: str) -> Dict[str, Any]:
    """
    Returns a human-readable summary of what features will be built
    for a given model type. Used by the UI to show users what signals
    will be extracted before training.
    """
    summaries = {
        "churn_prediction": {
            "primary_signals": ["recency", "frequency", "monetary (RFM)"],
            "derived_features": ["avg_order_value", "rfm_scores (1-5)", "support_count"],
            "target_column_hints": TARGET_HINTS["churn_prediction"],
            "accuracy_note": "Best accuracy when ≥500 rows with last_order_date and order_count.",
        },
        "clv_prediction": {
            "primary_signals": ["avg_order_value", "purchase_frequency", "tenure"],
            "derived_features": ["monthly_revenue_rate", "predicted_lifespan", "gross_margin_proxy"],
            "target_column_hints": TARGET_HINTS["clv_prediction"],
            "accuracy_note": "Best accuracy when historical CLV or LTV column is present.",
        },
        "lead_scoring": {
            "primary_signals": ["touchpoint_count", "email_opens", "page_views"],
            "derived_features": ["source_score", "stage_score", "days_since_last_touch"],
            "target_column_hints": TARGET_HINTS["lead_scoring"],
            "accuracy_note": "Best accuracy when conversion outcome column (converted/won) is present.",
        },
    }
    return summaries.get(model_type, {"note": "No summary available for this model type."})