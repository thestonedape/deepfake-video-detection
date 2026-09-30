import asyncio
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from jobs import Base,engine
async def migrate():
    async with engine.begin() as conn: await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()
if __name__=='__main__': asyncio.run(migrate())
