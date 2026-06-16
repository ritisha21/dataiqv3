import httpx, asyncio, sys
sys.path.insert(0, r"C:\Users\KIIT\Downloads\dataiq-platform\dataiqv3\dataiqv3\backend")
from app.core.security import create_access_token

async def get():
    token = create_access_token({"sub": "dev@dataiq.com", "tenant_id": "00000000-0000-0000-0000-000000000001", "role": "admin"})
    async with httpx.AsyncClient() as client:
        r = await client.get("http://localhost:8000/api/v1/connections/", headers={"Authorization": f"Bearer {token}"})
        for c in r.json():
            print(c["id"], c["name"])

asyncio.run(get())