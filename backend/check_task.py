path = r"C:\Users\KIIT\Downloads\dataiq-platform\dataiqv3\dataiqv3\backend\app\infrastructure\tasks\ml_tasks.py"
with open(path) as f:
    lines = f.readlines()
for i, line in enumerate(lines[44:80], start=44):
    print(i, repr(line))