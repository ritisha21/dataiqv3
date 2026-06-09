path = r"C:\Users\KIIT\Downloads\dataiq-platform\dataiqv3\dataiqv3\backend\app\infrastructure\ml_pipeline\pipeline.py"

with open(path, "r", encoding="utf-8") as f:
    lines = f.readlines()

# Replace lines 78-83 (drop object cols + fillna) with freq encoding
lines[78] = '        # Frequency-encode string columns and save maps for predict\n'
lines[79] = '        freq_maps = {}\n'
lines[80] = '        for col in X.columns:\n'
lines[81] = '            if X[col].dtype == object:\n'
lines.insert(82, '                freq_map = X[col].value_counts(normalize=True).to_dict()\n')
lines.insert(83, '                freq_maps[col] = freq_map\n')
lines.insert(84, '                X[col] = X[col].map(freq_map).fillna(0.0)\n')
lines.insert(85, '\n')

with open(path, "w", encoding="utf-8") as f:
    f.writelines(lines)

print("Patched training to use freq encoding!")

# Verify
with open(path, "r", encoding="utf-8") as f:
    lines = f.readlines()
for i, line in enumerate(lines[78:92], start=78):
    print(i, repr(line))