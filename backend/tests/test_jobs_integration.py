import asyncio
import os
import tempfile
from datetime import datetime, timedelta, timezone
import pytest

pytestmark=pytest.mark.skipif(not os.getenv('SDE_TEST_DATABASE_URL'),reason='Explicit isolated test database required')

def test_admission_capabilities_results_cache_and_recovery(monkeypatch):
    async def scenario():
        from sqlalchemy import delete
        from httpx import ASGITransport, AsyncClient
        from jobs import Job, Session, Base, engine
        from app import app
        from worker import infer_job, reconcile, WorkerSettings
        from arq.connections import create_pool
        assert engine.url.database.endswith('_test')
        assert engine.url.render_as_string(hide_password=False)==os.environ['SDE_TEST_DATABASE_URL']
        async with engine.begin() as db:await db.run_sync(Base.metadata.create_all)
        pool=await create_pool(WorkerSettings.redis_settings)
        monkeypatch.setenv('MAX_QUEUED_JOBS','1')
        paused=asyncio.Event();ids=[]
        class Inference:
            calls=0
            async def predict(self,path):
                self.calls+=1
                assert path.exists()
                if self.calls==1: paused.set();await asyncio.Event().wait()
                return {'predicted_label':'real','confidence':.8,'probabilities':{'fake':.2,'real':.8},'frame_count':10,'sampled_frames':10}
        try:
            with tempfile.TemporaryDirectory(prefix='deepfake-test-storage-') as folder:
                monkeypatch.setenv('LOCAL_STORAGE_DIR',folder)
                monkeypatch.setenv('ENVIRONMENT','development')
                async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as client:
                    video=b'\0\0\0\x18ftypmp42'+b'fixture'*20
                    response=await client.post('/jobs',files={'file':('fixture.mp4',video,'video/mp4')})
                    assert response.status_code==202
                    first=response.json();ids.append(first['job_id'])
                    assert (await client.get('/jobs/'+first['job_id'])).status_code==404
                    assert (await client.get('/jobs/'+first['job_id'],headers={'X-Job-Token':'wrong'})).status_code==404
                    assert (await client.post('/jobs',files={'file':('second.mp4',video+b'2','video/mp4')})).status_code==429
                    context={'inference':Inference()}
                    task=asyncio.create_task(infer_job(context,first['job_id']))
                    await asyncio.wait_for(paused.wait(),10);task.cancel();await asyncio.gather(task,return_exceptions=True)
                    async with Session() as db:
                        job=await db.get(Job,first['job_id']);job.lease_until=datetime.now(timezone.utc)-timedelta(seconds=1)
                        job.next_attempt_at=None;await db.commit()
                    await reconcile({'redis':pool})
                    await infer_job(context,first['job_id'])
                    await infer_job(context,first['job_id'])
                    result=await client.get('/jobs/'+first['job_id'],headers={'X-Job-Token':first['job_token']})
                    assert result.json()['status']=='completed' and context['inference'].calls==2
                    cached=await client.post('/jobs',files={'file':('fixture.mp4',video,'video/mp4')})
                    assert cached.status_code==202 and cached.json()['cached']
                    ids.append(cached.json()['job_id'])
                    assert cached.json()['job_token']!=first['job_token']
        finally:
            async with Session() as db:await db.execute(delete(Job).where(Job.id.in_(ids)));await db.commit()
            await pool.aclose();await engine.dispose()
    asyncio.run(scenario())
