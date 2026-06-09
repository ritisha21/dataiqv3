from typing import Dict, Any, Optional, Tuple, List
import pandas as pd
import numpy as np
import os
import joblib
import json
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import (
    roc_auc_score, f1_score, accuracy_score,
    mean_squared_error, mean_absolute_error, r2_score
)
import xgboost as xgb
from app.core.config import settings
from app.domain.models.models import ModelGoal
import structlog

logger = structlog.get_logger()

RANDOM_SEED = 42


class MLPipelineService:
    """
    Deterministic ML training pipeline.
    No LLM calls here. XGBoost baseline with experiment tracking.
    """

    def __init__(self):
        os.makedirs(settings.ML_MODEL_DIR, exist_ok=True)

    def train(
        self,
        df: pd.DataFrame,
        target_col: str,
        goal: ModelGoal,
        model_id: str,
        tenant_id: str,
        hyperparameters: Optional[Dict] = None,
        dataset_hash: Optional[str] = None,
        freq_maps: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """
        Returns {metrics, artifact_path, feature_importance, params}
        Raises on failure.
        """
        logger.info("ml_training_start", model_id=model_id, goal=goal, target=target_col)

        df = df.copy()

        # Drop remaining non-numeric non-target columns
        feature_cols = [c for c in df.columns if c != target_col]
        df = df[feature_cols + [target_col]].copy()

        # Remove rows with null target
        df = df.dropna(subset=[target_col])

        if len(df) < 50:
            raise ValueError("Insufficient data: need at least 50 rows")

        X = df[feature_cols]
        y = df[target_col]

        # Determine task type
        is_classification = goal in (ModelGoal.classification, ModelGoal.churn)
        if not is_classification:
            # Revenue forecast + regression
            is_classification = len(y.unique()) <= 10 and y.dtype in (object, "category", bool)

        # Encode target if classification
        le = None
        if is_classification and y.dtype == object:
            le = LabelEncoder()
            y = le.fit_transform(y)
        elif is_classification:
            y = y.astype(int)
        else:
            y = y.astype(float)

        # Frequency-encode string columns and save maps for predict
        freq_maps = {}
        for col in X.columns:
            if X[col].dtype == object:
                freq_map = X[col].value_counts(normalize=True).to_dict()
                freq_maps[col] = freq_map
                X[col] = X[col].map(freq_map).fillna(0.0)


        X = X.fillna(0).astype(float)

        # Train/test split
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=RANDOM_SEED
        )

        # Default hyperparameters
        default_params = {
            "n_estimators": 200,
            "max_depth": 6,
            "learning_rate": 0.1,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "random_state": RANDOM_SEED,
            "n_jobs": -1,
        }
        params = {**default_params, **(hyperparameters or {})}

        if is_classification:
            n_classes = len(np.unique(y_train))
            objective = "binary:logistic" if n_classes == 2 else "multi:softprob"
            extra_params = {"num_class": int(n_classes)} if n_classes > 2 else {}
            model = xgb.XGBClassifier(
                **params,
                **extra_params,
                objective=objective,
                use_label_encoder=False,
                eval_metric="logloss" if n_classes == 2 else "merror",
            )
            model.fit(
                X_train, y_train,
                eval_set=[(X_test, y_test)],
                verbose=False,
            )
            y_pred = model.predict(X_test)
            y_prob = model.predict_proba(X_test)

            if n_classes == 2:
                auc = roc_auc_score(y_test, y_prob[:, 1])
            else:
                auc = roc_auc_score(y_test, y_prob, multi_class="ovr")

            metrics = {
                "auc": round(float(auc), 4),
                "f1": round(float(f1_score(y_test, y_pred, average="weighted")), 4),
                "accuracy": round(float(accuracy_score(y_test, y_pred)), 4),
                "train_size": len(X_train),
                "test_size": len(X_test),
                "n_classes": int(n_classes),
            }
        else:
            model = xgb.XGBRegressor(**params)
            model.fit(
                X_train, y_train,
                eval_set=[(X_test, y_test)],
                verbose=False,
            )
            y_pred = model.predict(X_test)
            rmse = float(np.sqrt(mean_squared_error(y_test, y_pred)))
            mae = float(mean_absolute_error(y_test, y_pred))
            r2 = float(r2_score(y_test, y_pred))

            metrics = {
                "rmse": round(rmse, 4),
                "mae": round(mae, 4),
                "r2": round(r2, 4),
                "train_size": len(X_train),
                "test_size": len(X_test),
            }

        # Feature importance
        importance = {}
        if hasattr(model, "feature_importances_"):
            importance = dict(zip(
                X.columns.tolist(),
                [round(float(v), 4) for v in model.feature_importances_]
            ))
            importance = dict(sorted(importance.items(), key=lambda x: -x[1])[:20])

        # Save artifacts
        artifact_dir = os.path.join(settings.ML_MODEL_DIR, tenant_id, model_id)
        os.makedirs(artifact_dir, exist_ok=True)
        artifact_path = os.path.join(artifact_dir, "model.joblib")

        artifact = {
            "model": model,
            "label_encoder": le,
            "feature_cols": X.columns.tolist(),
            "is_classification": is_classification,
            "goal": goal.value,
            "freq_maps": freq_maps or {},
        }
        joblib.dump(artifact, artifact_path)

        # Save metadata
        meta_path = os.path.join(artifact_dir, "metadata.json")
        with open(meta_path, "w") as f:
            json.dump({
                "metrics": metrics,
                "params": params,
                "feature_importance": importance,
                "dataset_hash": dataset_hash,
                "feature_cols": X.columns.tolist(),
                "is_classification": is_classification,
            }, f)

        logger.info("ml_training_complete", model_id=model_id, metrics=metrics)

        return {
            "metrics": metrics,
            "artifact_path": artifact_path,
            "feature_importance": importance,
            "params": params,
            "feature_cols": X.columns.tolist(),
        }

    def predict(
        self,
        artifact_path: str,
        input_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Run inference on a trained model."""
        artifact = joblib.load(artifact_path)
        model = artifact["model"]
        le = artifact.get("label_encoder")
        feature_cols = artifact["feature_cols"]
        is_classification = artifact["is_classification"]

        df = pd.DataFrame([input_data])

        # Ensure correct columns
        for col in feature_cols:
            if col not in df.columns:
                df[col] = 0.0

        # Handle string columns — frequency encode using training data freq maps
        freq_maps = artifact.get("freq_maps", {})
        for col in df.columns:
            if df[col].dtype == object:
                if col in freq_maps:
                    df[col] = df[col].map(freq_maps[col]).fillna(0.0)
                else:
                    df[col] = 0.0
        df = df[feature_cols].fillna(0).astype(float)

        prediction = model.predict(df)[0]

        result = {}
        if is_classification:
            proba = model.predict_proba(df)[0]
            if le:
                prediction_label = le.inverse_transform([int(prediction)])[0]
            else:
                prediction_label = int(prediction)
            result = {
                "prediction": prediction_label,
                "probability": {str(i): round(float(p), 4) for i, p in enumerate(proba)},
                "confidence": round(float(max(proba)), 4),
            }
        else:
            result = {"prediction": round(float(prediction), 4)}

        return result


ml_pipeline = MLPipelineService()
