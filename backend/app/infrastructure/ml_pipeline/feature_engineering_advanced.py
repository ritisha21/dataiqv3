"""
backend/app/infrastructure/ml_pipeline/feature_engineering_advanced.py
───────────────────────────────────────────────────────────────────────
Advanced feature engineering for CRM string-heavy data:

1. Clubbed column detection — finds columns that contain multiple
   values concatenated (e.g. "New York, USA" or "CEO / Founder")
   and splits them into separate features.

2. Text-to-numeric conversion — TF-IDF on free-text columns,
   target encoding for high-cardinality categoricals.

3. Binary feature creation via logistic regression — uses L1
   logistic regression to generate a probability score feature
   from text/categorical columns against the target.

4. Textual-to-model-number — maps string categories to ordinal
   integers using frequency or target-mean ordering.

5. Interaction features — multiplies/combines numeric columns
   that are likely to have joint predictive power.
"""

from __future__ import annotations

import re
import hashlib
from typing import Dict, List, Optional, Tuple, Any

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import LabelEncoder

from app.core.logging import get_logger

logger = get_logger(__name__)

# ─── Constants ────────────────────────────────────────────────────────────────

# Separators that indicate a column is "clubbed" (contains multiple values)
CLUB_SEPARATORS = [",", "/", "|", ";", " & ", " and ", " + "]

# Columns with these substrings are likely free text — use TF-IDF
TEXT_HINTS = ["note", "comment", "description", "feedback", "reason",
              "summary", "detail", "message", "remark"]

# High-cardinality threshold — above this, use target encoding instead of one-hot
HIGH_CARDINALITY = 15

# TF-IDF max features per text column
TFIDF_MAX_FEATURES = 20


# ─── 1. Clubbed column splitter ───────────────────────────────────────────────

def detect_clubbed_columns(df: pd.DataFrame) -> Dict[str, str]:
    """
    Detect columns that contain multiple values concatenated.
    Returns {col_name: detected_separator}.
    """
    clubbed: Dict[str, str] = {}
    obj_cols = df.select_dtypes(include=["object"]).columns

    for col in obj_cols:
        sample = df[col].dropna().head(100).astype(str)
        for sep in CLUB_SEPARATORS:
            # If >30% of non-null values contain this separator, it's clubbed
            hit_rate = sample.str.contains(re.escape(sep), regex=False).mean()
            if hit_rate > 0.30:
                clubbed[col] = sep
                break

    if clubbed:
        logger.info("clubbed_columns_detected", cols=list(clubbed.keys()))
    return clubbed


def split_clubbed_columns(
    df: pd.DataFrame,
    clubbed: Dict[str, str],
    max_splits: int = 3,
) -> pd.DataFrame:
    """
    Split clubbed columns into multiple binary indicator columns.
    e.g. "New York, USA" → col_new_york=1, col_usa=1
    Original column is dropped.
    """
    df = df.copy()

    for col, sep in clubbed.items():
        # Collect all unique tokens
        all_tokens: List[str] = []
        for val in df[col].dropna().astype(str):
            parts = [p.strip().lower() for p in val.split(sep)]
            all_tokens.extend(parts)

        # Keep only the top-N most frequent tokens
        from collections import Counter
        token_counts = Counter(all_tokens)
        top_tokens = [t for t, _ in token_counts.most_common(max_splits * 3)
                      if t and len(t) > 1][:max_splits * 3]

        if not top_tokens:
            continue

        # Create binary indicator columns
        for token in top_tokens:
            safe_name = re.sub(r"[^a-z0-9_]", "_", token)
            new_col = f"{col}__{safe_name}"
            df[new_col] = df[col].fillna("").astype(str).str.lower().str.contains(
                re.escape(token), regex=False
            ).astype(float)

        df = df.drop(columns=[col])
        logger.info("clubbed_column_split", col=col, n_new_cols=len(top_tokens))

    return df


# ─── 2. Text-to-numeric via TF-IDF ───────────────────────────────────────────

def encode_text_columns(
    df: pd.DataFrame,
    text_cols: Optional[List[str]] = None,
) -> Tuple[pd.DataFrame, Dict[str, TfidfVectorizer]]:
    """
    Apply TF-IDF to free-text columns.
    Auto-detects text columns if not provided.
    Returns (transformed_df, {col: fitted_vectorizer}).
    """
    df = df.copy()
    vectorizers: Dict[str, TfidfVectorizer] = {}

    if text_cols is None:
        obj_cols = df.select_dtypes(include=["object"]).columns
        text_cols = [c for c in obj_cols
                     if any(h in c.lower() for h in TEXT_HINTS)]

    for col in text_cols:
        if col not in df.columns:
            continue

        corpus = df[col].fillna("").astype(str).tolist()
        if sum(len(t) for t in corpus) < 50:
            continue  # not enough text

        try:
            vec = TfidfVectorizer(
                max_features=TFIDF_MAX_FEATURES,
                strip_accents="unicode",
                lowercase=True,
                ngram_range=(1, 2),
            )
            tfidf_matrix = vec.fit_transform(corpus).toarray()
            feature_names = [f"{col}__tfidf_{f}" for f in vec.get_feature_names_out()]
            tfidf_df = pd.DataFrame(tfidf_matrix, columns=feature_names, index=df.index)

            df = pd.concat([df.drop(columns=[col]), tfidf_df], axis=1)
            vectorizers[col] = vec
            logger.info("tfidf_applied", col=col, n_features=len(feature_names))
        except Exception as exc:
            logger.warning("tfidf_failed", col=col, error=str(exc))
            df[col] = 0.0

    return df, vectorizers


# ─── 3. Logistic regression binary feature ───────────────────────────────────

def add_logistic_score_feature(
    df: pd.DataFrame,
    target_col: str,
    text_cols: Optional[List[str]] = None,
) -> Tuple[pd.DataFrame, Optional[Any]]:
    """
    Trains a simple L1 logistic regression on text/categorical columns
    and adds the predicted probability as a new feature 'lr_score'.

    This captures non-linear text signals in a single numeric feature
    that XGBoost can use directly.

    Returns (df_with_lr_score, fitted_lr_model_or_None).
    """
    df = df.copy()

    if target_col not in df.columns:
        return df, None

    y = pd.to_numeric(df[target_col], errors="coerce").fillna(0)
    if len(y.unique()) < 2:
        return df, None

    # Find string columns to use as input (excluding target)
    if text_cols is None:
        text_cols = [c for c in df.select_dtypes(include=["object"]).columns
                     if c != target_col]

    if not text_cols:
        return df, None

    try:
        # Combine all text columns into a single corpus
        corpus = df[text_cols].fillna("").astype(str).agg(" ".join, axis=1).tolist()
        vec = TfidfVectorizer(max_features=100, lowercase=True)
        X_text = vec.fit_transform(corpus)

        lr = LogisticRegression(
            C=0.1, penalty="l1", solver="liblinear",
            max_iter=200, random_state=42
        )
        y_binary = (y > y.median()).astype(int)
        lr.fit(X_text, y_binary)

        df["lr_score"] = lr.predict_proba(X_text)[:, 1]
        logger.info("lr_score_feature_added")
        return df, (lr, vec)
    except Exception as exc:
        logger.warning("lr_score_failed", error=str(exc))
        return df, None


# ─── 4. Textual-to-ordinal (text-to-model-number) ────────────────────────────

def encode_categorical_columns(
    df: pd.DataFrame,
    target_col: Optional[str] = None,
    cat_cols: Optional[List[str]] = None,
) -> Tuple[pd.DataFrame, Dict[str, Dict]]:
    """
    Encodes remaining string/categorical columns as numbers.

    Low cardinality (≤ HIGH_CARDINALITY unique values):
        → Frequency encoding (value → proportion of occurrences)

    High cardinality:
        → Target mean encoding if target_col provided, else frequency encoding

    Returns (df_encoded, {col: encoding_map}).
    """
    df = df.copy()
    encoding_maps: Dict[str, Dict] = {}

    if cat_cols is None:
        cat_cols = [c for c in df.select_dtypes(include=["object"]).columns
                    if c != target_col]

    for col in cat_cols:
        if col not in df.columns:
            continue

        n_unique = df[col].nunique()

        if target_col and target_col in df.columns and n_unique > HIGH_CARDINALITY:
            # Target mean encoding
            try:
                target_numeric = pd.to_numeric(df[target_col], errors="coerce")
                means = df.groupby(col)[target_col].apply(
                    lambda x: pd.to_numeric(x, errors="coerce").mean()
                ).to_dict()
                df[col] = df[col].map(means).fillna(target_numeric.mean())
                encoding_maps[col] = {"type": "target_mean", "map": means}
                logger.info("target_mean_encoded", col=col, n_unique=n_unique)
            except Exception:
                freq_map = df[col].value_counts(normalize=True).to_dict()
                df[col] = df[col].map(freq_map).fillna(0.0)
                encoding_maps[col] = {"type": "frequency", "map": freq_map}
        else:
            # Frequency encoding
            freq_map = df[col].value_counts(normalize=True).to_dict()
            df[col] = df[col].map(freq_map).fillna(0.0)
            encoding_maps[col] = {"type": "frequency", "map": freq_map}

    return df, encoding_maps


# ─── 5. Interaction features ──────────────────────────────────────────────────

def add_interaction_features(
    df: pd.DataFrame,
    target_col: Optional[str] = None,
    max_pairs: int = 5,
) -> pd.DataFrame:
    """
    Creates multiplicative interaction features between the most
    correlated numeric column pairs (excluding target).
    """
    df = df.copy()
    num_cols = [c for c in df.select_dtypes(include=[np.number]).columns
                if c != target_col and df[c].std() > 0]

    if len(num_cols) < 2:
        return df

    try:
        corr = df[num_cols].corr().abs()
        # Get upper triangle pairs sorted by correlation
        pairs = []
        for i in range(len(num_cols)):
            for j in range(i + 1, len(num_cols)):
                pairs.append((num_cols[i], num_cols[j], corr.iloc[i, j]))
        pairs.sort(key=lambda x: x[2], reverse=True)

        for a, b, _ in pairs[:max_pairs]:
            df[f"{a}__x__{b}"] = df[a] * df[b]

        logger.info("interaction_features_added", n_pairs=min(max_pairs, len(pairs)))
    except Exception as exc:
        logger.warning("interaction_features_failed", error=str(exc))

    return df


# ─── Public API ───────────────────────────────────────────────────────────────

def run_advanced_feature_engineering(
    df: pd.DataFrame,
    target_col: str,
    add_lr_score: bool = True,
    add_interactions: bool = True,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Full advanced feature engineering pipeline.
    Runs all steps in order and returns (transformed_df, artifact_dict).

    artifact_dict contains all fitted encoders/vectorizers needed
    to transform new data at prediction time.
    """
    artifact: Dict[str, Any] = {}
    original_cols = len(df.columns)

    # Step 1: Detect and split clubbed columns
    clubbed = detect_clubbed_columns(df)
    if clubbed:
        df = split_clubbed_columns(df, clubbed)
        artifact["clubbed_cols"] = clubbed

    # Step 2: TF-IDF on text columns
    df, text_vecs = encode_text_columns(df)
    if text_vecs:
        artifact["text_vectorizers"] = text_vecs

    # Step 3: Logistic regression score feature
    if add_lr_score:
        df, lr_artifact = add_logistic_score_feature(df, target_col)
        if lr_artifact:
            artifact["lr_score_model"] = lr_artifact

    # Step 4: Encode remaining categoricals
    df, enc_maps = encode_categorical_columns(df, target_col=target_col)
    artifact["encoding_maps"] = enc_maps

    # Step 5: Interaction features
    if add_interactions:
        df = add_interaction_features(df, target_col=target_col)

    # Final cleanup
    df = df.apply(pd.to_numeric, errors="coerce").fillna(0)

    logger.info(
        "advanced_feature_engineering_done",
        original_cols=original_cols,
        final_cols=len(df.columns),
        new_features=len(df.columns) - original_cols,
    )

    return df, artifact