import joblib, glob, os

model_dir = r"C:\tmp\dataiq\models\00000000-0000-0000-0000-000000000001"
files = glob.glob(os.path.join(model_dir, "**", "*.joblib"), recursive=True)
files.sort(key=os.path.getmtime, reverse=True)
artifact = joblib.load(files[0])
print("Model:", files[0].split("\\")[-2])
print("Feature columns:", artifact.get("feature_cols"))
print("Classes:", artifact.get("label_encoder").classes_)
print("Feature importances:")
for col, imp in zip(artifact.get("feature_cols"), artifact["model"].feature_importances_):
    print(f"  {col}: {imp:.4f}")