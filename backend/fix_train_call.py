path = r"C:\Users\KIIT\Downloads\dataiq-platform\dataiqv3\dataiqv3\backend\app\infrastructure\tasks\ml_tasks.py"

with open(path, "r", encoding="utf-8") as f:
    lines = f.readlines()

# Add freq_maps param after dataset_hash on line 73
lines[73] = '            dataset_hash=dataset_hash,\n            freq_maps=freq_maps,\n'

with open(path, "w", encoding="utf-8") as f:
    f.writelines(lines)

print("Patched train call!")