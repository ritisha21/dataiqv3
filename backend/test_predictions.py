import httpx, asyncio, sys
sys.path.insert(0, r"C:\Users\KIIT\Downloads\dataiq-platform\dataiqv3\dataiqv3\backend")
from app.core.security import create_access_token

async def test():
    token = create_access_token({"sub": "dev@dataiq.com", "tenant_id": "00000000-0000-0000-0000-000000000001", "role": "admin"})
    model_id = "045d346d-0712-4d60-9ec4-7075537975dc"
    
    tests = [
        {"sales_agent": "Anna Snelling", "product": "GTXPro", "close_value": 500, "created_date": 1483228800},
        {"sales_agent": "Anna Snelling", "product": "GTXPro", "close_value": 50000, "created_date": 1483228800},
        {"sales_agent": "Wilburn Farren", "product": "GTK 500", "close_value": 1000, "created_date": 1483228800},
    ]
    
    async with httpx.AsyncClient() as client:
        for t in tests:
            r = await client.post(
                "http://localhost:8000/api/v1/models/predict",
                json={"model_id": model_id, "input_data": t},
                headers={"Authorization": f"Bearer {token}"}
            )
            result = r.json().get("prediction", {})
            print(f"value={t['close_value']:>6} agent={t['sales_agent'][:12]:<12} → {result.get('prediction')} ({result.get('confidence', 0)*100:.1f}%)")

asyncio.run(test())
