from __future__ import annotations
import asyncio
import hashlib
import logging
import os
import secrets
import tempfile
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from fastapi import FastAPI, File, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, func, text
from jobs import Job, Session, engine, VERSION, token_digest, public_job
from storage import Storage
from observability import install_observability

MAX_UPLOAD_BYTES=100*1024*1024
ALLOWED_EXTENSIONS={'.mp4','.mov','.webm','.avi','.mkv'}
ALLOWED_MIMES={'video/mp4','video/quicktime','video/webm','video/x-msvideo','video/x-matroska','application/octet-stream'}
legacy_lock=asyncio.Lock()
dispatch_pool=None

async def dispatch_now(job_id):
    """Best-effort fast path after commit; worker reconciliation remains the guarantee."""
    global dispatch_pool
    try:
        if dispatch_pool is None:
            from arq.connections import create_pool
            from worker import WorkerSettings
            dispatch_pool=await asyncio.wait_for(create_pool(WorkerSettings.redis_settings),2)
        await asyncio.wait_for(dispatch_pool.enqueue_job('infer_job',job_id,_job_id=f'video:{job_id}:0',_queue_name='deepfake:queue'),2)
    except Exception:
        dispatch_pool=None

@asynccontextmanager
async def lifespan(app):
    yield
    await engine.dispose()

app=FastAPI(title='Deepfake Detector API',version='2.0.0',lifespan=lifespan)
origins=os.getenv('FRONTEND_ORIGINS','https://deepfake-ten-psi.vercel.app,http://localhost:5173,http://127.0.0.1:5173').split(',')
app.add_middleware(CORSMiddleware,allow_origins=[x.strip().rstrip('/') for x in origins],allow_credentials=False,allow_methods=['GET','POST','OPTIONS'],allow_headers=['Content-Type','X-Job-Token','X-Request-ID'])
install_observability(app)

@app.get('/')
def root(): return {'name':'Deepfake Detector API','status':'ok'}
@app.get('/health')
def health(): return {'status':'ok'}
@app.get('/ready')
async def ready():
    from arq.connections import create_pool
    from worker import WorkerSettings
    pool=None
    try:
        async with Session() as db: await db.execute(text('SELECT 1 FROM deepfake_jobs LIMIT 1'))
        pool=await create_pool(WorkerSettings.redis_settings);await pool.ping()
        storage=Storage()
        if not storage.local and not (storage.url and storage.key): raise RuntimeError('Storage not configured')
        worker = await pool.get('deepfake:worker:ready')
        if not worker: raise RuntimeError('Inference worker unavailable')
        return {'status':'ready','model_version':VERSION,'worker_model_status':'loaded'}
    except Exception as exc: raise HTTPException(503,'Job dependencies not ready') from exc
    finally:
        if pool: await pool.aclose()

async def receive(file,path):
    if not file.filename: raise HTTPException(400,'A video is required')
    suffix=Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS or file.content_type not in ALLOWED_MIMES:
        raise HTTPException(415,'Unsupported video format')
    matching_mime = {'.mp4':'video/mp4', '.mov':'video/quicktime', '.webm':'video/webm', '.avi':'video/x-msvideo', '.mkv':'video/x-matroska'}
    if file.content_type not in {matching_mime[suffix], 'application/octet-stream'}:
        raise HTTPException(415,'Video MIME type does not match its extension')
    size=0; digest=hashlib.sha256();head=b''
    with open(path,'wb') as output:
        while chunk:=await file.read(1024*1024):
            size+=len(chunk)
            if size>MAX_UPLOAD_BYTES: raise HTTPException(413,'File exceeds 100 MB limit')
            if len(head)<32: head+=chunk[:32-len(head)]
            digest.update(chunk);output.write(chunk)
    valid=(suffix in {'.mp4','.mov'} and b'ftyp' in head[:32]) or (suffix in {'.webm','.mkv'} and head.startswith(b'\x1aE\xdf\xa3')) or (suffix=='.avi' and head.startswith(b'RIFF') and head[8:12]==b'AVI ')
    if not valid: raise HTTPException(422,'Video signature does not match its extension')
    if size==0: raise HTTPException(422,'Video is empty')
    return digest.hexdigest()

@app.post('/jobs',status_code=202)
async def create_job(file: UploadFile=File(...)):
    job_id=str(uuid.uuid4());token=secrets.token_urlsafe(32)
    key=f'jobs/{job_id}{Path(file.filename or "").suffix.lower()}'
    storage=Storage();stored=False
    try:
        with tempfile.TemporaryDirectory(prefix='deepfake-upload-') as directory:
            path=Path(directory)/'upload'
            content_hash=await receive(file,path)
            async with Session() as db:
                # Cross-process admission serialization; uploads/cache hits still get isolated capabilities.
                await db.execute(text('SELECT pg_advisory_xact_lock(7300930)'))
                cached=await db.scalar(select(Job).where(Job.content_hash==content_hash,Job.version==VERSION,Job.status=='completed').order_by(Job.completed_at.desc()).limit(1))
                queued=await db.scalar(select(func.count()).select_from(Job).where(Job.status.in_(['queued','processing'])))
                if not cached and queued>=int(os.getenv('MAX_QUEUED_JOBS','20')): raise HTTPException(429,'Inference queue is full',headers={'Retry-After':'10'})
                if not cached:
                    await storage.put(key,path,file.content_type);stored=True
                job=Job(id=job_id,token_hash=token_digest(token),content_hash=content_hash,object_key=key,filename=Path(file.filename).name[:255],version=VERSION,status='completed' if cached else 'queued',result=cached.result if cached else None,completed_at=datetime.now(timezone.utc) if cached else None,cleanup_pending=not bool(cached))
                db.add(job);await db.commit()
            if not cached: await dispatch_now(job_id)
            return {**public_job(job),'job_token':token,'cached':bool(cached)}
    except HTTPException: raise
    except Exception as exc:
        if stored:
            try: await storage.delete(key)
            except Exception: pass
        raise HTTPException(503,'Unable to persist job; retry later') from exc
    finally: await file.close()

@app.get('/jobs/{job_id}')
async def get_job(job_id:str,x_job_token:str=Header(default='')):
    async with Session() as db:
        job=await db.get(Job,job_id)
        if not job or not secrets.compare_digest(job.token_hash,token_digest(x_job_token)):
            raise HTTPException(404,'Job not found')
        return public_job(job)

@app.post('/predict')
async def predict(file:UploadFile=File(...)):
    if legacy_lock.locked():
        await file.close()
        raise HTTPException(429,'Inference is busy',headers={'Retry-After':'2'})
    async with legacy_lock:
        filename = file.filename
        accepted = await create_job(file)
        # Compatibility uses the same bounded worker as /jobs, never a second model.
        for _ in range(30):
            job = await get_job(accepted['job_id'], accepted['job_token'])
            if job['status'] == 'completed': return {'filename':filename, **job['result']}
            if job['status'] == 'failed': raise HTTPException(422,'Video cannot be decoded or analyzed')
            await asyncio.sleep(1)
        from starlette.responses import JSONResponse
        return JSONResponse(accepted, status_code=202)
