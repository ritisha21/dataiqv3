# Fix pipeline.py - ensure input_freq_maps is saved correctly
pipeline_path = r"C:\Users\KIIT\Downloads\dataiq-platform\dataiqv3\dataiqv3\backend\app\infrastructure\ml_pipeline\pipeline.py"

with open(pipeline_path, "r", encoding="utf-8") as f:
    content = f.read()

# Nuclear option - replace the entire artifact dict
old = '"model": model,'
new = '"model": model,\n            "freq_maps": input_freq_maps or {},'

# Only add if not already there
if '"freq_maps": input_freq_maps' not in content:
    content = content.replace(old, new, 1)
    print("Added freq_maps to artifact")
else:
    print("Already present")

with open(pipeline_path, "w", encoding="utf-8") as f:
    f.write(content)

# Verify
with open(pipeline_path, "r", encoding="utf-8") as f:
    for i, line in enumerate(f):
        if "freq_maps" in line or "input_freq_maps" in line:
            print(f"Line {i}: {line.rstrip()}")