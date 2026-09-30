import asyncio
import json
import os
import sys
import tempfile
import shutil
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
import httpx
from arq import cron
from arq.connections import RedisSettings
from sqlalchemy import select, or_, and_
from jobs import Job, Session
from storage import Storage
JOB_TEMP_ROOT=Path(tempfile.gettempdir())/'deepfake-inference'
INFERENCE_TIMEOUT_SECONDS=int(os.getenv('INFERENCE_TIMEOUT_SECONDS','300'))

class InferenceProcess:
    def __init__(self): self.process=None
    async def close(self):
        if self.process and self.process.returncode is None:
            self.process.kill(); await self.process.wait()
        self.process=None
    async def start(self):
        if self.process is None or self.process.returncode is not None:
            self.process=await asyncio.create_subprocess_exec(sys.executable,'-u',str(Path(__file__).parent/'inference_runner.py'),stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE)
            ready=await asyncio.wait_for(self.process.stdout.readline(),180)
            if not ready or not json.loads(ready).get('ready'): raise RuntimeError('Model not ready')
    async def predict(self,path):
        try:
            await self.start()
            self.process.stdin.write((json.dumps({'path':str(path)})+'\n').encode());await self.process.stdin.drain()
            line=await asyncio.wait_for(self.process.stdout.readline(),INFERENCE_TIMEOUT_SECONDS)
            payload=json.loads(line)
            if 'error' in payload: raise ValueError(payload['error'])
            return payload['result']
        except ValueError:
            # A decoded child error keeps its already-loaded model alive.
            if self.process and self.process.returncode is None:
                raise
            await self.close()
            raise
        except (asyncio.CancelledError,Exception):
            await self.close();raise

async def worker_ready(ctx):
    process=ctx['inference'].process
    if process and process.returncode is None:
        await ctx['redis'].set('deepfake:worker:ready', '1', ex=45)
    else:
        await ctx['redis'].delete('deepfake:worker:ready')

async def startup(ctx):
    JOB_TEMP_ROOT.mkdir(parents=True,exist_ok=True)
    # Dedicated single-worker scratch root; durable uploads live in storage.
    for candidate in JOB_TEMP_ROOT.iterdir():
        if candidate.is_dir() and candidate.resolve().is_relative_to(JOB_TEMP_ROOT.resolve()):
            shutil.rmtree(candidate)
    ctx['inference']=InferenceProcess()
    try:
        await ctx['inference'].start()
        await worker_ready(ctx)
        ctx['presence'] = asyncio.create_task(presence(ctx))
    except Exception:
        await ctx['inference'].close()
        raise
async def shutdown(ctx):
    ctx['presence'].cancel()
    await asyncio.gather(ctx['presence'], return_exceptions=True)
    await ctx['redis'].delete('deepfake:worker:ready')
    await ctx['inference'].close()

async def presence(ctx):
    while True:
        try:
            await worker_ready(ctx)
        except Exception:
            pass
        await asyncio.sleep(15)

async def reconcile(ctx):
    now=datetime.now(timezone.utc)
    async with Session() as db:
        jobs=(await db.scalars(select(Job).where(or_(Job.status=='queued',and_(Job.status=='processing',Job.lease_until<now))).limit(20).with_for_update(skip_locked=True))).all()
        for job in jobs:
            if job.next_attempt_at and job.next_attempt_at>now: continue
            if job.attempts>=3:
                job.status='failed';job.error='RetryLimitExceeded';job.completed_at=now;continue
            if job.status=='processing': job.status='queued';job.lease=None
            try:
                await ctx['redis'].enqueue_job('infer_job',job.id,_job_id=f'video:{job.id}:{job.attempts}',_queue_name='deepfake:queue')
                job.dispatched_at=now
            except Exception: pass
            job.next_attempt_at=now+timedelta(seconds=30)
        await db.commit()
    async with Session() as db:
        terminal=(await db.scalars(select(Job).where(Job.status.in_(['completed','failed']),Job.cleanup_pending.is_(True)).limit(20))).all()
        for job in terminal:
            try:
                await Storage().delete(job.object_key)
                job.cleanup_pending=False
            except Exception:
                pass
        await db.commit()

async def pulse(job_id,lease):
    while True:
        await asyncio.sleep(10)
        async with Session() as db:
            job=await db.scalar(select(Job).where(Job.id==job_id).with_for_update())
            if not job or job.lease!=lease: return
            job.lease_until=datetime.now(timezone.utc)+timedelta(seconds=60)
            await db.commit()

async def infer_job(ctx,job_id):
    lease=str(uuid.uuid4());now=datetime.now(timezone.utc)
    async with Session() as db:
        job=await db.scalar(select(Job).where(Job.id==job_id).with_for_update())
        if not job or job.status in {'completed','failed'} or (job.lease_until and job.lease_until>now): return
        job.status='processing';job.lease=lease;job.lease_until=now+timedelta(seconds=60);job.attempts+=1
        key=job.object_key; filename=job.filename
        await db.commit()
    ticker=asyncio.create_task(pulse(job_id,lease))
    try:
        JOB_TEMP_ROOT.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=lease+'-',dir=JOB_TEMP_ROOT) as directory:
            path=Path(directory)/('video'+Path(filename).suffix.lower())
            await Storage().get(key,path)
            result=await ctx['inference'].predict(path)
        async with Session() as db:
            job=await db.scalar(select(Job).where(Job.id==job_id).with_for_update())
            owned_terminal = False
            if job and job.lease==lease:
                job.result=result;job.status='completed';job.completed_at=datetime.now(timezone.utc);job.lease=None;job.lease_until=None
                await db.commit()
                owned_terminal = True
        # Uploaded originals are not retained after inference. Metadata/result cache survives.
        if owned_terminal:
            try: await Storage().delete(key)
            except Exception: pass  # reconciliation below retries cleanup
    except Exception as exc:
        retryable=isinstance(exc,httpx.TransportError) or isinstance(exc,httpx.HTTPStatusError) and (exc.response.status_code==429 or exc.response.status_code>=500)
        async with Session() as db:
            job=await db.scalar(select(Job).where(Job.id==job_id).with_for_update())
            if job and job.lease==lease:
                job.status='queued' if retryable and job.attempts<3 else 'failed'
                job.error=type(exc).__name__;job.lease=None;job.lease_until=None
                if job.status=='failed': job.completed_at=datetime.now(timezone.utc)
                job.next_attempt_at=datetime.now(timezone.utc)+timedelta(seconds=5*4**max(0,job.attempts-1))
                await db.commit()
                terminal=job.status=='failed'
            else: terminal=False
        if terminal:
            try: await Storage().delete(key)
            except Exception: pass
    finally:
        ticker.cancel();await asyncio.gather(ticker,return_exceptions=True)

class WorkerSettings:
    queue_name='deepfake:queue'
    functions=[infer_job]
    cron_jobs=[cron(reconcile,second={0,15,30,45},run_at_startup=True)]
    redis_settings=RedisSettings.from_dsn(os.getenv('REDIS_URL','redis://localhost:6379/0'))
    on_startup=startup
    on_shutdown=shutdown
    max_jobs=1
    job_timeout=600
    keep_result=0
    poll_delay=0.5  # one-slot worker: idle polling, not inference, dominated queue wait
