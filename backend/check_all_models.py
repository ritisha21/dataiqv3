import joblib, glob, os

model_dir = r"C:\tmp\dataiq\models"
files = glob.glob(os.path.join(model_dir, "**", "*.joblib"), recursive=True)
files.sort(key=os.path.getmtime, reverse=True)

for f in files:
    mtime = os.path.getmtime(f)
    artifact = joblib.load(f)
    fm = artifact.get("freq_maps", {})
    ifm = artifact.get("input_freq_maps")
    print(f"{f}")
    print(f"  freq_maps keys: {list(fm.keys())}")
    print(f"  input_freq_maps: {ifm is not None}")
    print()