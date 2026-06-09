import joblib, glob, os

model_dir = r"C:\tmp\dataiq\models"
files = glob.glob(os.path.join(model_dir, "**", "*.joblib"), recursive=True) + \
        glob.glob(os.path.join(model_dir, "**", "*.pkl"), recursive=True)

print("Model files found:", files)

if files:
    artifact = joblib.load(files[-1])
    print("Feature cols:", artifact.get("feature_cols"))
    print("Keys:", list(artifact.keys()))