path = r"C:\Users\KIIT\Downloads\dataiq-platform\dataiqv3\dataiqv3\backend\app\infrastructure\ml_pipeline\pipeline.py"

with open(path, "r", encoding="utf-8") as f:
    lines = f.readlines()

# Add freq_maps param to signature after dataset_hash (line 39)
lines[39] = '        dataset_hash: Optional[str] = None,\n        freq_maps: Optional[Dict] = None,\n'

# Find the artifact dict and add freq_maps to it
for i, line in enumerate(lines):
    if '"goal": goal.value,' in line:
        lines[i] = '            "goal": goal.value,\n            "freq_maps": freq_maps or {},\n'
        print(f"Patched artifact at line {i}")
        break

with open(path, "w", encoding="utf-8") as f:
    f.writelines(lines)

print("Patched train signature!")

# Verify artifact section
with open(path, "r", encoding="utf-8") as f:
    lines = f.readlines()
for i, line in enumerate(lines):
    if "freq_maps" in line:
        print(f"Line {i}: {repr(line)}")