path = r"C:\Users\KIIT\Downloads\dataiq-platform\dataiqv3\dataiqv3\backend\app\infrastructure\ml_pipeline\pipeline.py"
with open(path) as f:
    lines = f.readlines()
for i, line in enumerate(lines[75:100], start=75):
    print(i, repr(line))