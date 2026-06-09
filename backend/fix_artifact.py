path = r"C:\Users\KIIT\Downloads\dataiq-platform\dataiqv3\dataiqv3\backend\app\infrastructure\ml_pipeline\pipeline.py"

with open(path, "r", encoding="utf-8") as f:
    lines = f.readlines()

# Add freq_maps to artifact at line 173 (after "goal": goal.value)
lines[173] = '            "goal": goal.value,\n            "freq_maps": freq_maps if "freq_maps" in dir() else {},\n'

# Now find where freq_maps is built in feature_store and pass it back
# For now, build freq_maps from X before training
# Find the line where X, y are split - look for train_test_split
for i, line in enumerate(lines):
    if "train_test_split" in line:
        print(f"Line {i}: {repr(line)}")

with open(path, "w", encoding="utf-8") as f:
    f.writelines(lines)

print("Patched artifact to include freq_maps!")