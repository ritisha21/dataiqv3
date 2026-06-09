import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from app.core.security import create_access_token

async def get_token():
    token = create_access_token(data={
        "sub": "dev@dataiq.com",
        "tenant_id": "00000000-0000-0000-0000-000000000001",
        "tenant_slug": "dev",
        "role": "admin"
    })
    print("Token:", token)

asyncio.run(get_token())