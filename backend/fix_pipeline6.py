path = r"C:\Users\KIIT\Downloads\dataiq-platform\dataiqv3\dataiqv3\backend\app\infrastructure\ml_pipeline\pipeline.py"

with open(path, "r", encoding="utf-8") as f:
    lines = f.readlines()

# Print lines around eval_metric to see exact content
for i, line in enumerate(lines):
    if "eval_metric" in line or "n_classes" in line or "XGBClassifier" in line:
        print(f"Line {i}: {repr(line)}")