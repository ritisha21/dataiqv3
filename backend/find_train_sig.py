path = r"C:\Users\KIIT\Downloads\dataiq-platform\dataiqv3\dataiqv3\backend\app\infrastructure\ml_pipeline\pipeline.py"
with open(path) as f:
    lines = f.readlines()
for i, line in enumerate(lines[30:60], start=30):
    print(i, repr(line))