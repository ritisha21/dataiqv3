path = r"C:\Users\KIIT\Downloads\dataiq-platform\dataiqv3\dataiqv3\frontend\src\lib\api.ts"

with open(path, "r", encoding="utf-8") as f:
    content = f.read()

old = "  connect:      (data: any)  => api.post('/connections/connect-db', data),"
new = "  connect:      (data: any)  => api.post('/connections/connect-db', data),\n  testConnection: (data: any) => api.post('/connections/test-connection', data),"

if old in content:
    content = content.replace(old, new)
    print("Patched api.ts")
else:
    print("ERROR: marker not found")

with open(path, "w", encoding="utf-8") as f:
    f.write(content)