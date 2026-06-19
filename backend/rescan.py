import httpx, asyncio, sys
sys.path.insert(0, r"C:\Users\KIIT\Downloads\dataiq-platform\dataiqv3\dataiqv3\backend")
from app.core.security import create_access_token

async def scan():
    token = create_access_token({"sub": "dev@dataiq.com", "tenant_id": "00000000-0000-0000-0000-000000000001", "role": "admin"})
    async with httpx.AsyncClient() as client:
        r = await client.get("http://localhost:8000/api/v1/connections/", headers={"Authorization": f"Bearer {token}"})
        conns = r.json()
        for c in conns:
            print(c["id"], c["name"])
            r2 = await client.post(f"http://localhost:8000/api/v1/connections/{c['id']}/re-introspect", headers={"Authorization": f"Bearer {token}"})
            print("  scan:", r2.status_code, r2.text[:80])

asyncio.run(scan())