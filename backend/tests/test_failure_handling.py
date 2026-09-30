"""Retry classification and scratch cleanup against the real job ledger."""
import asyncio
import os
import uuid
import pytest

pytestmark=pytest.mark.skipif(not os.getenv('SDE_TEST_DATABASE_URL'),reason='Explicit isolated test database required')

def test_storage_outage_retries_then_fails_and_corrupt_media_fails_once(monkeypatch):
    async def scenario():
        import httpx
        from sqlalchemy import delete
        from jobs import Job, Session, Base, engine, VERSION
        import worker
        assert engine.url.database.endswith('_test')
        async with engine.begin() as db:await db.run_sync(Base.metadata.create_all)
        deleted=[]
        async def unreachable(self,key,path):raise httpx.ConnectError('storage unreachable')
        async def forget(self,key):deleted.append(key)
        monkeypatch.setattr(worker.Storage,'get',unreachable)
        monkeypatch.setattr(worker.Storage,'delete',forget)
        ids=[str(uuid.uuid4()),str(uuid.uuid4())]
        try:
            async with Session() as db:
                for n,job_id in enumerate(ids):
                    db.add(Job(id=job_id,token_hash='0'*64,content_hash=str(n)*64,object_key=f'k{n}',filename='v.mp4',version=VERSION,status='queued'))
                await db.commit()
            # Transient storage outage: requeued with growing backoff, then failed at the attempt limit.
            delays=[]
            for attempt in range(1,4):
                await worker.infer_job({'inference':None},ids[0])
                async with Session() as db:
                    job=await db.get(Job,ids[0])
                    assert job.attempts==attempt and job.error=='ConnectError' and job.lease is None
                    assert job.status==('queued' if attempt<3 else 'failed')
                    delays.append((job.next_attempt_at-job.created_at).total_seconds())
            assert delays[0]<delays[1]<delays[2]
            assert deleted==['k0']  # original removed only once terminal
            # Deterministic decode failure: no retry, one attempt, original cleaned up.
            async def fetched(self,key,path):path.write_bytes(b'corrupt')
            monkeypatch.setattr(worker.Storage,'get',fetched)
            class CorruptInference:
                async def predict(self,path):raise ValueError('Unsupported video dimensions, length or codec')
            await worker.infer_job({'inference':CorruptInference()},ids[1])
            async with Session() as db:
                job=await db.get(Job,ids[1])
                assert job.status=='failed' and job.attempts==1 and job.error=='ValueError'
            assert deleted==['k0','k1']
            # Scratch directories vanish after success or failure.
            assert not any(worker.JOB_TEMP_ROOT.iterdir())
        finally:
            async with Session() as db:await db.execute(delete(Job).where(Job.id.in_(ids)));await db.commit()
            await engine.dispose()
    asyncio.run(scenario())
