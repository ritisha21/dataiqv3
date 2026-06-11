path = r"C:\Users\KIIT\Downloads\dataiq-platform\dataiqv3\dataiqv3\backend\app\infrastructure\ml_pipeline\pipeline.py"

with open(path, "r", encoding="utf-8") as f:
    lines = f.readlines()

# Line 40: rename parameter to input_freq_maps
lines[40] = '        input_freq_maps: Optional[Dict] = None,\n'

# Line 179: use input_freq_maps instead of local freq_maps
lines[179] = '            "freq_maps": input_freq_maps or {},\n'

with open(path, "w", encoding="utf-8") as f:
    f.writelines(lines)

# Verify
with open(path, "r", encoding="utf-8") as f:
    lines = f.readlines()
print("Line 40:", repr(lines[40]))
print("Line 179:", repr(lines[179]))