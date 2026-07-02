"""
backend/app/infrastructure/ml_pipeline/multi_trainer.py
─────────────────────────────────────────────────────────
Trains multiple model types on the same dataset, tracks each run
with MLflow, and returns an accuracy leaderboard so the client
can pick the best model.

Models trained per task type:
  Classification: XGBoost, LogisticRegression, RandomForest, LightGBM
  Regression:     XGBoost, Ridge, RandomForest, LightGBM

Usage:
    from app.infrastructure.ml_pipeline.multi_trainer import train_multiple_models
    leaderboard, best = train_multiple_models(df, target_col, goal, model_id, tenant_id)
"""

from __future__ import annotations

import os
import time
import json
import joblib
from typing import Dict, Any, List, Tuple, Optional

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import (
    roc_auc_score, f1_score, accuracy_score,
    mean_squared_error, mean_absolute_error, r2_score,
)
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
import xgboost as xgb

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)
RANDOM_SEED = 42

# ── Try to import optional heavy deps ─────────────────────────────────────────
try:
    import lightgbm as lgb
    HAS_LGB = True
except ImportError:
    HAS_LGB = False

try:
    import mlflow
    import mlflow.sklearn
    import mlflow.xgboost
    HAS_MLFLOW = True
except ImportError:
    HAS_MLFLOW = False


# ─── Model definitions ────────────────────────────────────────────────────────

def _get_classifiers(n_classes: int) -> List[Tuple[str, Any]]:
    objective = "binary:logistic" if n_classes == 2 else "multi:softprob"
    extra = {"num_class": n_classes} if n_classes > 2 else {}

    models = [
        ("XGBoost", xgb.XGBClassifier(
            n_estimators=100, max_depth=5, learning_rate=0.1,
            subsample=0.8, colsample_bytree=0.8,
            objective=objective, use_label_encoder=False,
            eval_metric="logloss", random_state=RANDOM_SEED,
            n_jobs=-1, **extra,
        )),
        ("LogisticRegression", LogisticRegression(
            C=1.0, max_iter=500, random_state=RANDOM_SEED, n_jobs=-1,
        )),
        ("RandomForest", RandomForestClassifier(
            n_estimators=100, max_depth=8, random_state=RANDOM_SEED, n_jobs=-1,
        )),
    ]

    if HAS_LGB:
        models.append(("LightGBM", lgb.LGBMClassifier(
            n_estimators=100, max_depth=5, learning_rate=0.1,
            random_state=RANDOM_SEED, n_jobs=-1, verbose=-1,
        )))

    return models


def _get_regressors() -> List[Tuple[str, Any]]:
    models = [
        ("XGBoost", xgb.XGBRegressor(
            n_estimators=100, max_depth=5, learning_rate=0.1,
            subsample=0.8, colsample_bytree=0.8,
            random_state=RANDOM_SEED, n_jobs=-1,
        )),
        ("Ridge", Ridge(alpha=1.0, random_state=RANDOM_SEED)),
        ("RandomForest", RandomForestRegressor(
            n_estimators=100, max_depth=8, random_state=RANDOM_SEED, n_jobs=-1,
        )),
    ]

    if HAS_LGB:
        models.append(("LightGBM", lgb.LGBMRegressor(
            n_estimators=100, max_depth=5, learning_rate=0.1,
            random_state=RANDOM_SEED, n_jobs=-1, verbose=-1,
        )))

    return models


# ─── MLflow helpers ───────────────────────────────────────────────────────────

def _setup_mlflow(experiment_name: str) -> None:
    if not HAS_MLFLOW:
        return
    mlflow_uri = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000")
    try:
        mlflow.set_tracking_uri(mlflow_uri)
        mlflow.set_experiment(experiment_name)
    except Exception as exc:
        logger.warning("mlflow_setup_failed", error=str(exc))


def _log_to_mlflow(
    run_name: str,
    params: Dict,
    metrics: Dict,
    model: Any,
    model_type: str,
) -> Optional[str]:
    if not HAS_MLFLOW:
        return None
    try:
        with mlflow.start_run(run_name=run_name):
            mlflow.log_params(params)
            mlflow.log_metrics({k: v for k, v in metrics.items() if isinstance(v, (int, float))})
            if "xgboost" in model_type.lower():
                mlflow.xgboost.log_model(model, "model")
            else:
                mlflow.sklearn.log_model(model, "model")
            return mlflow.active_run().info.run_id
    except Exception as exc:
        logger.warning("mlflow_log_failed", error=str(exc))
        return None


# ─── Main multi-trainer ───────────────────────────────────────────────────────

def train_multiple_models(
    df: pd.DataFrame,
    target_col: str,
    goal: str,
    model_id: str,
    tenant_id: str,
    experiment_name: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Train multiple model types and return a leaderboard.

    Returns
    -------
    leaderboard : list of dicts, sorted by primary metric descending
        Each entry: {model_name, metrics, artifact_path, mlflow_run_id, rank}

    best : the top leaderboard entry (dict with all fields above)
    """
    if experiment_name is None:
        experiment_name = f"dataiq/{tenant_id}/{goal}"

    _setup_mlflow(experiment_name)

    feature_cols = [c for c in df.columns if c != target_col]
    X = df[feature_cols].copy()
    y = df[target_col].copy()

    is_classification = goal in ("churn", "classification", "churn_prediction", "lead_scoring")
    if not is_classification:
        is_classification = y.nunique() <= 10 and y.dtype in (object, "category", bool)

    # Encode target
    le = None
    if is_classification and y.dtype == object:
        le = LabelEncoder()
        y = pd.Series(le.fit_transform(y), index=y.index)
    elif is_classification:
        y = y.astype(int)
    else:
        y = y.astype(float)

    n_classes = int(y.nunique()) if is_classification else 0

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=RANDOM_SEED
    )

    models = _get_classifiers(n_classes) if is_classification else _get_regressors()
    artifact_dir = os.path.join(settings.ML_MODEL_DIR, tenant_id, model_id)
    os.makedirs(artifact_dir, exist_ok=True)

    leaderboard: List[Dict[str, Any]] = []

    for model_name, model in models:
        logger.info("multi_trainer_start", model=model_name, goal=goal)
        t0 = time.time()

        try:
            if "XGBoost" in model_name:
                model.fit(
                    X_train, y_train,
                    eval_set=[(X_test, y_test)],
                    verbose=False,
                )
            else:
                model.fit(X_train, y_train)

            elapsed = round(time.time() - t0, 2)

            # ── Compute metrics ───────────────────────────────────────────────
            if is_classification:
                y_pred = model.predict(X_test)
                y_prob = model.predict_proba(X_test)
                if n_classes == 2:
                    auc = float(roc_auc_score(y_test, y_prob[:, 1]))
                else:
                    auc = float(roc_auc_score(y_test, y_prob, multi_class="ovr"))
                metrics = {
                    "auc":       round(auc, 4),
                    "f1":        round(float(f1_score(y_test, y_pred, average="weighted")), 4),
                    "accuracy":  round(float(accuracy_score(y_test, y_pred)), 4),
                    "train_size": len(X_train),
                    "test_size":  len(X_test),
                    "train_time_s": elapsed,
                }
                primary_metric = "auc"
            else:
                y_pred = model.predict(X_test)
                rmse = float(np.sqrt(mean_squared_error(y_test, y_pred)))
                metrics = {
                    "rmse":       round(rmse, 4),
                    "mae":        round(float(mean_absolute_error(y_test, y_pred)), 4),
                    "r2":         round(float(r2_score(y_test, y_pred)), 4),
                    "train_size": len(X_train),
                    "test_size":  len(X_test),
                    "train_time_s": elapsed,
                }
                primary_metric = "r2"

            # ── Feature importance ────────────────────────────────────────────
            importance: Dict[str, float] = {}
            if hasattr(model, "feature_importances_"):
                importance = dict(zip(
                    X.columns.tolist(),
                    [round(float(v), 4) for v in model.feature_importances_]
                ))
                importance = dict(sorted(importance.items(), key=lambda x: -x[1])[:20])

            # ── Save artifact ─────────────────────────────────────────────────
            artifact_path = os.path.join(artifact_dir, f"{model_name}.joblib")
            joblib.dump({
                "model":             model,
                "label_encoder":     le,
                "feature_cols":      X.columns.tolist(),
                "is_classification": is_classification,
                "goal":              goal,
                "model_name":        model_name,
                "freq_maps":         {},
            }, artifact_path)

            # ── MLflow logging ────────────────────────────────────────────────
            run_id = _log_to_mlflow(
                run_name=f"{model_name}_{model_id[:8]}",
                params={"model_type": model_name, "goal": goal, "n_features": len(feature_cols)},
                metrics=metrics,
                model=model,
                model_type=model_name,
            )

            leaderboard.append({
                "model_name":      model_name,
                "metrics":         metrics,
                "primary_metric":  primary_metric,
                "primary_score":   metrics[primary_metric],
                "artifact_path":   artifact_path,
                "mlflow_run_id":   run_id,
                "feature_importance": importance,
            })

            logger.info("multi_trainer_done", model=model_name, metrics=metrics)

        except Exception as exc:
            logger.error("multi_trainer_failed", model=model_name, error=str(exc))
            leaderboard.append({
                "model_name":    model_name,
                "error":         str(exc),
                "primary_score": -999,
            })

    # ── Sort leaderboard ──────────────────────────────────────────────────────
    leaderboard.sort(key=lambda x: x.get("primary_score", -999), reverse=True)
    for i, entry in enumerate(leaderboard):
        entry["rank"] = i + 1

    best = leaderboard[0] if leaderboard else {}

    # ── Save leaderboard JSON ─────────────────────────────────────────────────
    leaderboard_path = os.path.join(artifact_dir, "leaderboard.json")
    with open(leaderboard_path, "w") as f:
        json.dump(leaderboard, f, default=str)

    logger.info(
        "multi_trainer_leaderboard",
        best_model=best.get("model_name"),
        best_score=best.get("primary_score"),
        n_models=len(leaderboard),
    )

    return leaderboard, best