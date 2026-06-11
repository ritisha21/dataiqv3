path = r"C:\Users\KIIT\Downloads\dataiq-platform\dataiqv3\dataiqv3\backend\app\infrastructure\tasks\ml_tasks.py"

with open(path, "r", encoding="utf-8") as f:
    lines = f.readlines()

# Replace freq_maps loop to use raw_df copy
lines[47] = '        # Build freq_maps from raw df COPY before any transformation\n'
lines[48] = '        raw_df = df.copy()\n'
lines[49] = '        freq_maps = {}\n'
lines[50] = '        for col in raw_df.select_dtypes(include=["object"]).columns:\n'
lines[51] = '            if col != training_config["target_col"]:\n'
lines.insert(52, '                freq_maps[col] = raw_df[col].value_counts(normalize=True).to_dict()\n')

with open(path, "w", encoding="utf-8") as f:
    f.writelines(lines)

print("Patched!")

with open(path) as f:
    lines = f.readlines()
for i, line in enumerate(lines[45:58], start=45):
    print(i, repr(line))