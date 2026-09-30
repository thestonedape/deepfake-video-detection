import asyncio
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from jobs import Base,engine
from sqlalchemy import text
async def migrate():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Backend ledger is private even if the provider's Data API is later enabled.
        policies = await conn.scalar(text("SELECT count(*) FROM pg_policies WHERE schemaname='public' AND tablename='deepfake_jobs'"))
        if policies:
            raise RuntimeError('Private ledger has unexpected row access policies; review before migration')
        await conn.execute(text('ALTER TABLE deepfake_jobs ENABLE ROW LEVEL SECURITY'))
    await engine.dispose()
if __name__=='__main__': asyncio.run(migrate())
