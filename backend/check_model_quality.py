import joblib, glob, os
import pandas as pd

model_dir = r"C:\tmp\dataiq\models"
files = glob.glob(os.path.join(model_dir, "**", "*.joblib"), recursive=True)
files.sort(key=os.path.getmtime, reverse=True)

artifact = joblib.load(files[0])
model = artifact['model']
le = artifact['label_encoder']
feature_cols = artifact['feature_cols']

print("Feature columns:", feature_cols)
print("Classes:", le.classes_)
print("Feature importances:")
for col, imp in zip(feature_cols, model.feature_importances_):
    print(f"  {col}: {imp:.4f}")