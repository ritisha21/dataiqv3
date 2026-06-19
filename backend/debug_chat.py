import asyncio
import httpx

TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJkZXZAZGF0YWlxLmNvbSIsInRlbmFudF9pZCI6IjAwMDAwMDAwLTAwMDAtMDAwMC0wMDAwLTAwMDAwMDAwMDAwMSIsInRlbmFudF9zbHVnIjoiZGV2Iiwicm9sZSI6ImFkbWluIiwiZXhwIjoxNzgxODQ4NjI0LCJ0eXBlIjoiYWNjZXNzIn0.jlGvMnM2SUrJeEbKa1OMLGNjK-68hUShoj_wKAHptEI"
async def test():
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "http://localhost:8000/api/v1/chat/",
            json={
                "connection_id": "83cacbd9-4a21-44e4-a30d-38c97966cbde",
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
