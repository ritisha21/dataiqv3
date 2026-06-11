path = r"C:\Users\KIIT\Downloads\dataiq-platform\dataiqv3\dataiqv3\backend\app\infrastructure\tasks\ml_tasks.py"

with open(path, "r", encoding="utf-8") as f:
    content = f.read()

# Fix whatever mangled version exists
import re
content = re.sub(r'input_(?:input_)*freq_maps=freq_maps,', 'input_freq_maps=freq_maps,', content)

with open(path, "w", encoding="utf-8") as f:
    f.write(content)

# Verify
with open(path, "r", encoding="utf-8") as f:
    for i, line in enumerate(f):
        if "freq_maps" in line:
            print(f"Line {i}: {repr(line)}")