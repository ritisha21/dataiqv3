import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def fix():
    engine = create_async_engine('postgresql+asyncpg://postgres:postgres@localhost:5432/dataiq')
    async with engine.begin() as conn:
        await conn.execute(text('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"'))
        await conn.execute(text('ALTER TABLE schema_snapshots ALTER COLUMN id SET DEFAULT uuid_generate_v4()'))
        print('Fixed!')

asyncio.run(fix())