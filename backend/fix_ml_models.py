import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def fix():
    engine = create_async_engine('postgresql+asyncpg://postgres:postgres@localhost:5432/dataiq')
    async with engine.begin() as conn:
        # Fix ml_models id default
        await conn.execute(text('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"'))
        await conn.execute(text('ALTER TABLE ml_models ALTER COLUMN id SET DEFAULT uuid_generate_v4()'))
        # Also fix ml_experiments just in case
        await conn.execute(text('ALTER TABLE ml_experiments ALTER COLUMN id SET DEFAULT uuid_generate_v4()'))
        print('Fixed ml_models and ml_experiments!')
        
        # Show current ml_models columns
        result = await conn.execute(text("""
            SELECT column_name, column_default 
            FROM information_schema.columns 
            WHERE table_name = 'ml_models'
        """))
        for row in result:
            print(row)

asyncio.run(fix())