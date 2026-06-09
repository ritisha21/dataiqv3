path = r"C:\Users\KIIT\Downloads\dataiq-platform\dataiqv3\dataiqv3\backend\app\infrastructure\tasks\ml_tasks.py"

with open(path, "r", encoding="utf-8") as f:
    lines = f.readlines()

# Insert freq_maps building after line 45 (dataset_hash), before line 48 (build_features)
insert_at = 46
new_lines = [
    '\n',
    '        # Build freq_maps from raw df before feature_store transforms string cols\n',
    '        freq_maps = {}\n',
    '        for col in df.select_dtypes(include=["object"]).columns:\n',
    '            if col != training_config["target_col"]:\n',
    '                freq_maps[col] = df[col].value_counts(normalize=True).to_dict()\n',
    '\n',
]

for i, line in enumerate(new_lines):
    lines.insert(insert_at + i, line)

# Now find pipeline.train call and add freq_maps to it
with open(path, "w", encoding="utf-8") as f:
    f.writelines(lines)

# Verify
with open(path, "r", encoding="utf-8") as f:
    lines = f.readlines()
for i, line in enumerate(lines[44:75], start=44):
    print(i, repr(line))