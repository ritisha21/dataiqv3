path = r"C:\Users\KIIT\Downloads\dataiq-platform\dataiqv3\dataiqv3\backend\app\infrastructure\ml_pipeline\pipeline.py"

with open(path, "r", encoding="utf-8") as f:
    lines = f.readlines()

# Replace line 218 with proper encoding
lines[218] = '''        # Handle string columns — frequency encode using training data freq maps
        freq_maps = artifact.get("freq_maps", {})
        for col in df.columns:
            if df[col].dtype == object:
                if col in freq_maps:
                    df[col] = df[col].map(freq_maps[col]).fillna(0.0)
                else:
                    df[col] = 0.0
        df = df[feature_cols].fillna(0).astype(float)
'''

with open(path, "w", encoding="utf-8") as f:
    f.writelines(lines)

print("Patched predict method!")