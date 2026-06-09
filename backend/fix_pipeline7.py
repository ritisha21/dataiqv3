path = r"C:\Users\KIIT\Downloads\dataiq-platform\dataiqv3\dataiqv3\backend\app\infrastructure\ml_pipeline\pipeline.py"

with open(path, "r", encoding="utf-8") as f:
    lines = f.readlines()

# Insert after line 104 (index 104) and fix line 109 (index 109)
# First fix eval_metric line (line 109)
lines[109] = '                eval_metric="logloss" if n_classes == 2 else "merror",\n'

# Insert num_class and eval_metric lines after objective line (line 104)
lines.insert(105, '            extra_params = {"num_class": int(n_classes)} if n_classes > 2 else {}\n')

# Now XGBClassifier is at line 106, add **extra_params
# Find the **params line (was 106, now 107 after insert)
for i, line in enumerate(lines):
    if '**params,' in line and i > 104:
        lines.insert(i + 1, '                **extra_params,\n')
        break

with open(path, "w", encoding="utf-8") as f:
    f.writelines(lines)

print("Patched successfully!")

# Verify
with open(path, "r", encoding="utf-8") as f:
    lines = f.readlines()
for i, line in enumerate(lines[100:115], start=100):
    print(f"Line {i}: {line}", end="")