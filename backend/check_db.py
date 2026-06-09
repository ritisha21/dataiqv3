import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def get_connections():
    engine = create_async_engine('postgresql+asyncpg://postgres:postgres@localhost:5432/dataiq')
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'db_connections' ORDER BY ordinal_position"))
        print('Columns:', [r[0] for r in result])
        result2 = await conn.execute(text('SELECT * FROM db_connections LIMIT 5'))
        for row in result2:
            print(row)

asyncio.run(get_connections())