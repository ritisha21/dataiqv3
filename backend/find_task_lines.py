path = r"C:\Users\KIIT\Downloads\dataiq-platform\dataiqv3\dataiqv3\backend\app\infrastructure\tasks\ml_tasks.py"
with open(path) as f:
    lines = f.readlines()
for i, line in enumerate(lines):
    if "build_features" in line or "pipeline.train" in line or "feature_df" in line or "dataset_hash" in line:
        print(i, repr(line))