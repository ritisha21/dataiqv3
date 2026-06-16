import joblib, os

model_id = "045d346d-0712-4d60-9ec4-7075537975dc"
tenant_id = "00000000-0000-0000-0000-000000000001"
path = rf"C:\tmp\dataiq\models\{tenant_id}\{model_id}\model.joblib"

if not os.path.exists(path):
    print("Model not trained yet - wait for worker to finish")
else:
    artifact = joblib.load(path)
    print("Feature columns:", artifact.get("feature_cols"))
    print("Classes:", artifact.get("label_encoder").classes_)
    print("Feature importances:")
    model = artifact.get("model")
    for col, imp in zip(artifact.get("feature_cols"), model.feature_importances_):
        print(f"  {col}: {imp:.4f}")
    print("freq_maps keys:", list(artifact.get("freq_maps", {}).keys()))
