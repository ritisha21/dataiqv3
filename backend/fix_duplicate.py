path = r"C:\Users\KIIT\Downloads\dataiq-platform\dataiqv3\dataiqv3\backend\app\infrastructure\ml_pipeline\pipeline.py"

with open(path, "r", encoding="utf-8") as f:
    lines = f.readlines()

# Remove the duplicate line 180
if 'freq_maps if "freq_maps" in dir()' in lines[180]:
    lines.pop(180)
    print("Removed duplicate line 180")

with open(path, "w", encoding="utf-8") as f:
    f.writelines(lines)