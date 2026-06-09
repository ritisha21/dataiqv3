path = r"C:\Users\KIIT\Downloads\dataiq-platform\dataiqv3\dataiqv3\backend\app\infrastructure\ml_pipeline\pipeline.py"

with open(path, "r", encoding="utf-8") as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if "def predict" in line:
        print(f"Line {i}: {repr(line)}")
    if "df = pd.DataFrame([input_data])" in line:
        print(f"Line {i}: {repr(line)}")
    if "df = df[feature_cols].fillna(0).astype(float)" in line:
        print(f"Line {i}: {repr(line)}")