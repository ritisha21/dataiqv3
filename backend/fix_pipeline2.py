path = r"C:\Users\KIIT\Downloads\dataiq-platform\dataiqv3\dataiqv3\backend\app\infrastructure\ml_pipeline\pipeline.py"

with open(path, "r", encoding="utf-8") as f:
    content = f.read()

# Find and show context around eval_metric
idx = content.find('eval_metric="logloss"')
if idx == -1:
    print("Cannot find eval_metric line")
else:
    print(repr(content[idx-200:idx+50]))