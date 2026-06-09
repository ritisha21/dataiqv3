import asyncio
import httpx

TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJkZXZAZGF0YWlxLmNvbSIsInRlbmFudF9pZCI6IjAwMDAwMDAwLTAwMDAtMDAwMC0wMDAwLTAwMDAwMDAwMDAwMSIsInRlbmFudF9zbHVnIjoiZGV2Iiwicm9sZSI6ImFkbWluIiwiZXhwIjoxNzgwOTk2MzE5LCJ0eXBlIjoiYWNjZXNzIn0.VrTuLVYCNoOk-1H5Te3wpnY8yX0QPeKHQjbwUyC4pY4"
async def test():
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "http://localhost:8000/api/v1/chat/",
            json={
                "connection_id": "f0ab1c5c-bb3d-4dbc-9e5e-732b4bc764de",
                "message": "Train a churn prediction model on the sales_pipeline table using deal_stage as the target"
            },
            headers={"Authorization": f"Bearer {TOKEN}"}, 
            timeout=300
        )
        print("Status:", resp.status_code)
        data = resp.json()
        print("Text:", data.get("text"))
        print("ML task:", data.get("ml_task"))
        print("Node errors:", data.get("execution_path"))

asyncio.run(test()) 