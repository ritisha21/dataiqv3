path = r"C:\Users\KIIT\Downloads\dataiq-platform\dataiqv3\dataiqv3\backend\app\infrastructure\tasks\ml_tasks.py"

with open(path, "r", encoding="utf-8") as f:
    content = f.read()

content = content.replace("freq_maps=freq_maps,", "input_freq_maps=freq_maps,")

with open(path, "w", encoding="utf-8") as f:
    f.write(content)

print("Patched ml_tasks!")