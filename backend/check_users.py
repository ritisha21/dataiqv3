import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def check():
    engine = create_async_engine('postgresql+asyncpg://postgres:postgres@localhost:5432/dataiq')
    async with engine.connect() as conn:
        result = await conn.execute(text('SELECT email, hashed_password FROM users LIMIT 5'))
        for row in result:
            print(row)

asyncio.run(check())