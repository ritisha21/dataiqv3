path = r"C:\Users\KIIT\Downloads\dataiq-platform\dataiqv3\dataiqv3\backend\app\infrastructure\ml_pipeline\pipeline.py"
with open(path) as f:
    lines = f.readlines()
for i, line in enumerate(lines[55:90], start=55):
    print(i, repr(line))