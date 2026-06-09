import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def fix():
    engine = create_async_engine('postgresql+asyncpg://postgres:postgres@localhost:5432/dataiq')
    async with engine.begin() as conn:
        await conn.execute(text(
            "UPDATE users SET email = 'dev@dataiq.com' WHERE email = 'dev@dataiq.local'"
        ))
        print('Email updated to dev@dataiq.com')

asyncio.run(fix())