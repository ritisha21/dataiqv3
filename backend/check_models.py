import joblib, glob, os

model_dir = r"C:\tmp\dataiq\models"
files = glob.glob(os.path.join(model_dir, "**", "*.joblib"), recursive=True)
files.sort(key=os.path.getmtime, reverse=True)

for f in files[:3]:
    print(f)
    artifact = joblib.load(f)
    print("  Keys:", list(artifact.keys()))
    print("  freq_maps:", list(artifact.get("freq_maps", {}).keys()))
    print()