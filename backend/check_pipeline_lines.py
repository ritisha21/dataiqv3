# Fix pipeline.py
pipeline_path = r"C:\Users\KIIT\Downloads\dataiq-platform\dataiqv3\dataiqv3\backend\app\infrastructure\ml_pipeline\pipeline.py"

with open(pipeline_path, "r", encoding="utf-8") as f:
    lines = f.readlines()

# Show current line 40 and artifact lines
for i, line in enumerate(lines):
    if i == 40 or "freq_maps" in line:
        print(f"Line {i}: {repr(line)}")