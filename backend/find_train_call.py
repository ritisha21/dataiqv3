path = r"C:\Users\KIIT\Downloads\dataiq-platform\dataiqv3\dataiqv3\backend\app\infrastructure\tasks\ml_tasks.py"
with open(path) as f:
    lines = f.readlines()
for i, line in enumerate(lines[60:80], start=60):
    print(i, repr(line))