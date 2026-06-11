import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def fix():
    engine = create_async_engine('postgresql+asyncpg://postgres:postgres@localhost:5432/dataiq')
    async with engine.begin() as conn:
        await conn.execute(text("ALTER TABLE ml_models ALTER COLUMN status TYPE modelstatus USING status::modelstatus"))
        print('Fixed!')

asyncio.run(fix())