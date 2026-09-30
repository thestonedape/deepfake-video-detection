import asyncio
import hashlib
import json
import httpx
import pytest
from storage import Storage


def test_large_original_roundtrip_integrity_and_cleanup(tmp_path, monkeypatch):
    monkeypatch.delenv('LOCAL_STORAGE_DIR', raising=False)
    monkeypatch.setenv('SUPABASE_URL','https://fixture.invalid')
    monkeypatch.setenv('SUPABASE_SERVICE_ROLE_KEY','fixture')
    objects={};real_client=httpx.AsyncClient
    def handle(request):
        path=request.url.path
        if '/bucket/' in path: return httpx.Response(200,json={'public':False})
        if request.method=='POST':
            assert len(request.content)<=4*1024*1024
            objects[path]=request.content
            return httpx.Response(200,json={})
        if request.method=='DELETE':
            objects.pop(path,None)
            return httpx.Response(200,json={})
        return httpx.Response(200,content=objects[path]) if path in objects else httpx.Response(404)
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kw: real_client(transport=httpx.MockTransport(handle),**kw))
    source=tmp_path/'original';output=tmp_path/'download'
    # Sparse fixture crosses the provider's single-object limit without keeping it in memory.
    with source.open('wb') as f: f.seek(51*1024*1024-1);f.write(b'x')
    async def scenario():
        storage=Storage()
        await storage.put('jobs/test.mp4',source,'video/mp4')
        assert len(objects)==14
        await storage.get('jobs/test.mp4',output)
        with source.open('rb') as f: original=hashlib.file_digest(f,'sha256').hexdigest()
        with output.open('rb') as f: assert hashlib.file_digest(f,'sha256').hexdigest()==original
        first=next(p for p in objects if p.endswith('.parts/00'))
        objects[first]=b'corrupt'
        with pytest.raises(RuntimeError,match='integrity'):
            await storage.get('jobs/test.mp4',output)
        await storage.delete('jobs/test.mp4')
        assert not objects
    asyncio.run(scenario())


def test_partial_chunk_upload_is_cleaned(tmp_path, monkeypatch):
    monkeypatch.delenv('LOCAL_STORAGE_DIR',raising=False)
    monkeypatch.setenv('SUPABASE_URL','https://fixture.invalid')
    monkeypatch.setenv('SUPABASE_SERVICE_ROLE_KEY','fixture')
    objects={};real_client=httpx.AsyncClient
    def handle(request):
        path=request.url.path
        if '/bucket/' in path: return httpx.Response(200,json={'public':False})
        if request.method=='DELETE': objects.pop(path,None);return httpx.Response(200)
        if request.method=='POST':
            objects[path]=request.content
            if path.endswith('/01'): raise httpx.ReadError('Transient storage failure')
            return httpx.Response(200)
        return httpx.Response(404)
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kw: real_client(transport=httpx.MockTransport(handle),**kw))
    source=tmp_path/'original'
    with source.open('wb') as f: f.seek(51*1024*1024-1);f.write(b'x')
    async def scenario():
        with pytest.raises(httpx.ReadError): await Storage().put('jobs/test.mp4',source,'video/mp4')
        assert not objects
    asyncio.run(scenario())
