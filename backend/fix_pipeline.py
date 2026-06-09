path = r"C:\Users\KIIT\Downloads\dataiq-platform\dataiqv3\dataiqv3\backend\app\infrastructure\ml_pipeline\pipeline.py"

with open(path, "r", encoding="utf-8") as f:
    content = f.read()

old = '''            objective = "binary:logistic" if n_classes == 2 else "multi:softprob"
              model = xgb.XGBClassifier(
                  **params,
                  objective=objective,
                  use_label_encoder=False,
                  eval_metric="logloss",
              )'''

new = '''            objective = "binary:logistic" if n_classes == 2 else "multi:softprob"
              eval_metric = "logloss" if n_classes == 2 else "merror"
              extra_params = {"num_class": n_classes} if n_classes > 2 else {}
              model = xgb.XGBClassifier(
                  **params,
                  **extra_params,
                  objective=objective,
                  use_label_encoder=False,
                  eval_metric=eval_metric,
              )'''

if old in content:
    content = content.replace(old, new)
    print("Patched successfully!")
else:
    print("ERROR: block not found — check indentation")

with open(path, "w", encoding="utf-8") as f:
    f.write(content)