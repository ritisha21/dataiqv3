import joblib, glob, os

model_dir = r"C:\tmp\dataiq\models"
files = glob.glob(os.path.join(model_dir, "**", "*.joblib"), recursive=True)
files.sort(key=os.path.getmtime, reverse=True)

artifact = joblib.load(files[0])
print("freq_maps type:", type(artifact.get("freq_maps")))
print("freq_maps:", artifact.get("freq_maps"))
print("feature_cols:", artifact.get("feature_cols"))