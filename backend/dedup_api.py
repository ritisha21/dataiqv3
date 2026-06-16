path = r"C:\Users\KIIT\Downloads\dataiq-platform\dataiqv3\dataiqv3\frontend\src\lib\api.ts"

with open(path, "r", encoding="utf-8") as f:
    content = f.read()

line = "  testConnection: (data: any) => api.post('/connections/test-connection', data),\n"
count = content.count(line)
print(f"Found {count} copies")
if count == 2:
    content = content.replace(line, '', 1)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("Removed duplicate")