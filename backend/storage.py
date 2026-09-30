import os
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
        async def chunks():
            with open(path,'rb') as f:
                while chunk:=f.read(1024*1024): yield chunk
        async with httpx.AsyncClient(timeout=120) as client:
            privacy=await client.get(f'{self.url}/storage/v1/bucket/{quote(self.bucket,safe="")}',headers=self.headers())
            privacy.raise_for_status()
            if privacy.json().get('public') is not False: raise RuntimeError('Video bucket must be private')
            response=await client.post(self.endpoint(key),headers={**self.headers(),'Content-Type':mime},content=chunks())
            response.raise_for_status()
    async def get(self,key,path):
        if self.local:
            import shutil
            shutil.copyfile(Path(self.local)/key,path); return
        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream('GET',self.endpoint(key),headers=self.headers()) as response:
                response.raise_for_status()
                with open(path,'wb') as file:
                    async for chunk in response.aiter_bytes(): file.write(chunk)
    async def delete(self,key):
        if self.local:
            (Path(self.local)/key).unlink(missing_ok=True); return
        async with httpx.AsyncClient(timeout=30) as client:
            response=await client.delete(self.endpoint(key),headers=self.headers())
            if response.status_code!=404: response.raise_for_status()
