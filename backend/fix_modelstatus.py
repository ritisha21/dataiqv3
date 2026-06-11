import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def fix():
    engine = create_async_engine('postgresql+asyncpg://postgres:postgres@localhost:5432/dataiq')
    async with engine.begin() as conn:
        await conn.execute(text("CREATE TYPE modelstatus AS ENUM ('pending', 'training', 'ready', 'failed')"))
        print('Fixed!')

asyncio.run(fix())