import joblib

artifact = joblib.load(r"C:\tmp\dataiq\models\00000000-0000-0000-0000-000000000001\30f30f65-7ba8-4390-b705-6bfab8953e21\model.joblib")
print("Keys:", list(artifact.keys()))
print("Feature cols:", artifact.get("feature_cols"))
print("Is classification:", artifact.get("is_classification"))