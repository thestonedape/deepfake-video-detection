import os
import hashlib
import json
from pathlib import Path
from urllib.parse import quote
import httpx

class Storage:
    def __init__(self):
        self.url=os.getenv('SUPABASE_URL','').rstrip('/')
        self.key=os.getenv('SUPABASE_SERVICE_ROLE_KEY','')
        self.bucket=os.getenv('SUPABASE_VIDEO_BUCKET','deepfake-videos')
        self.local=os.getenv('LOCAL_STORAGE_DIR')
        if self.local and os.getenv('ENVIRONMENT')=='production':
            raise RuntimeError('Local storage is not durable in production')
    def headers(self):
        return {'Authorization':f'Bearer {self.key}','apikey':self.key}
    def endpoint(self,key):
        return f'{self.url}/storage/v1/object/{quote(self.bucket,safe="")}/{quote(key,safe="/")}'
    async def put(self,key,path,mime):
        if self.local:
            import shutil
            dest=Path(self.local)/key; dest.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(path,dest); return
        if not self.url or not self.key: raise RuntimeError('Object storage not configured')
        # Free Supabase limits each object to 50 MB. Large originals are a
        # bounded sequence of 4 MiB objects with a manifest committed last.
        async with httpx.AsyncClient(timeout=120) as client:
            privacy=await client.get(f'{self.url}/storage/v1/bucket/{quote(self.bucket,safe="")}',headers=self.headers())
            privacy.raise_for_status()
            if privacy.json().get('public') is not False: raise RuntimeError('Video bucket must be private')
            size=Path(path).stat().st_size
            if size <= 45*1024*1024:
                async def chunks():
                    with open(path,'rb') as source:
                        while chunk:=source.read(1024*1024): yield chunk
                response=await client.post(self.endpoint(key),headers={**self.headers(),'Content-Type':mime},content=chunks())
                response.raise_for_status()
                return
            uploaded=[];digest=hashlib.sha256()
            try:
                with open(path,'rb') as source:
                    while chunk:=source.read(4*1024*1024):
                        part=f'{key}.parts/{len(uploaded):02d}'
                        # Include the attempted object in cleanup for ambiguous network failures.
                        uploaded.append(part);digest.update(chunk)
                        response=await client.post(self.endpoint(part),headers={**self.headers(),'Content-Type':'application/octet-stream'},content=chunk)
                        response.raise_for_status()
                manifest={'version':1,'parts':len(uploaded),'size':size,'sha256':digest.hexdigest()}
                response=await client.post(self.endpoint(key+'.manifest.json'),headers={**self.headers(),'Content-Type':'application/json'},content=json.dumps(manifest).encode())
                response.raise_for_status()
            except Exception:
                for part in [*uploaded,key+'.manifest.json']:
                    try: await client.delete(self.endpoint(part),headers=self.headers())
                    except httpx.HTTPError: pass
                raise

    async def manifest(self,client,key):
        response=await client.get(self.endpoint(key+'.manifest.json'),headers=self.headers())
        if response.status_code==404: return None
        response.raise_for_status()
        value=response.json()
        if value.get('version')!=1 or not isinstance(value.get('parts'),int) or not 1<=value['parts']<=25 or not isinstance(value.get('size'),int) or not 0<value['size']<=100*1024*1024:
            raise RuntimeError('Invalid video storage manifest')
        return value

    async def get(self,key,path):
        if self.local:
            import shutil
            shutil.copyfile(Path(self.local)/key,path); return
        async with httpx.AsyncClient(timeout=120) as client:
            manifest=await self.manifest(client,key)
            keys=[f'{key}.parts/{i:02d}' for i in range(manifest['parts'])] if manifest else [key]
            digest=hashlib.sha256();size=0
            with open(path,'wb') as output:
                for part in keys:
                    async with client.stream('GET',self.endpoint(part),headers=self.headers()) as response:
                        response.raise_for_status()
                        async for chunk in response.aiter_bytes():
                            size+=len(chunk)
                            if size>100*1024*1024: raise RuntimeError('Stored video exceeds limit')
                            digest.update(chunk);output.write(chunk)
            if manifest and (size!=manifest['size'] or digest.hexdigest()!=manifest['sha256']):
                raise RuntimeError('Stored video integrity check failed')
    async def delete(self,key):
        if self.local:
            (Path(self.local)/key).unlink(missing_ok=True); return
        async with httpx.AsyncClient(timeout=30) as client:
            manifest=await self.manifest(client,key)
            keys=[f'{key}.parts/{i:02d}' for i in range(manifest['parts'])]+[key+'.manifest.json'] if manifest else [key]
            for part in keys:
                response=await client.delete(self.endpoint(part),headers=self.headers())
                if response.status_code!=404: response.raise_for_status()
