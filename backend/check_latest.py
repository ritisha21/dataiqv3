import joblib, glob, os

model_dir = r"C:\tmp\dataiq\models"
files = glob.glob(os.path.join(model_dir, "**", "*.joblib"), recursive=True)
files.sort(key=os.path.getmtime, reverse=True)

print("Most recent model:")
print(files[0])
print("Modified:", os.path.getmtime(files[0]))

artifact = joblib.load(files[0])
print("freq_maps:", artifact.get("freq_maps"))
print("input_freq_maps:", artifact.get("input_freq_maps"))