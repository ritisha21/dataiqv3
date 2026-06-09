path = r"C:\Users\KIIT\Downloads\dataiq-platform\dataiqv3\dataiqv3\backend\app\infrastructure\ml_pipeline\pipeline.py"

with open(path, "r", encoding="utf-8") as f:
    content = f.read()

old = 'objective = "binary:logistic" if n_classes == 2 else "multi:softprob"\n            model = xgb.XGBClassifier(\n     **params,\n                objective=objective,\n                use_label_encoder=False,\n              eval_metric="logloss",\n            )'

new = 'objective = "binary:logistic" if n_classes == 2 else "multi:softprob"\n            eval_metric = "logloss" if n_classes == 2 else "merror"\n            extra_params = {"num_class": int(n_classes)} if n_classes > 2 else {}\n            model = xgb.XGBClassifier(\n     **params,\n                **extra_params,\n                objective=objective,\n                use_label_encoder=False,\n              eval_metric=eval_metric,\n            )'

if old in content:
    content = content.replace(old, new)
    print("Patched successfully!")
else:
    print("ERROR: still not found")

with open(path, "w", encoding="utf-8") as f:
    f.write(content)