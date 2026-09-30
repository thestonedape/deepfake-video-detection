import asyncio
import io
import pytest
from fastapi import HTTPException, UploadFile
from starlette.datastructures import Headers
from app import receive

def upload(data,name='a.mp4',mime='video/mp4'):
    return UploadFile(io.BytesIO(data),filename=name,headers=Headers({'content-type':mime}))
@pytest.mark.parametrize('data,name,mime,status',[(b'bad','a.txt','text/plain',415),(b'bad','a.mp4','video/mp4',422),(b'RIFFxxxxAVI xxxx','a.mp4','video/mp4',422)])
def test_rejected_upload(tmp_path,data,name,mime,status):
    with pytest.raises(HTTPException) as error: asyncio.run(receive(upload(data,name,mime),tmp_path/'video'))
    assert error.value.status_code==status

def test_streamed_hash(tmp_path):
    data=b'\x00\x00\x00\x18ftypmp42'+b'0'*100
    import hashlib
    assert asyncio.run(receive(upload(data),tmp_path/'video'))==hashlib.sha256(data).hexdigest()

def test_upload_limit(tmp_path,monkeypatch):
    monkeypatch.setattr('app.MAX_UPLOAD_BYTES',10)
    with pytest.raises(HTTPException) as error: asyncio.run(receive(upload(b'\0\0\0\x18ftypmp42'),tmp_path/'video'))
    assert error.value.status_code==413
