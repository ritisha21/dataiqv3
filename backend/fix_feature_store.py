path = r"C:\Users\KIIT\Downloads\dataiq-platform\dataiqv3\dataiqv3\backend\app\infrastructure\feature_store\feature_store.py"

with open(path, "r", encoding="utf-8") as f:
    content = f.read()

old = '        use_dask = len(df) > DASK_THRESHOLD'

new = '''        # Convert datetime columns to numeric (unix timestamp) before any processing
        for col in df.select_dtypes(include=["datetime64[ns]", "datetimetz"]).columns:
            df[col] = df[col].astype("int64") // 10**9  # seconds since epoch

        use_dask = len(df) > DASK_THRESHOLD'''

if old in content:
    content = content.replace(old, new)
    print("Patched datetime fix!")
else:
    print("ERROR: block not found")

with open(path, "w", encoding="utf-8") as f:
    f.write(content)