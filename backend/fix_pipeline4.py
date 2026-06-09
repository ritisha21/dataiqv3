path = r"C:\Users\KIIT\Downloads\dataiq-platform\dataiqv3\dataiqv3\backend\app\infrastructure\ml_pipeline\pipeline.py"

with open(path, "r", encoding="utf-8") as f:
    content = f.read()

idx = content.find('eval_metric="logloss"')
print(repr(content[idx-300:idx+100]))