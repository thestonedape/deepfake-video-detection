import asyncio
import json
import pytest
import worker

class Input:
    def write(self,data):self.last=data
    async def drain(self):pass

class Output:
    def __init__(self,lines):self.lines=list(lines)
    async def readline(self):
        if self.lines:return json.dumps(self.lines.pop(0)).encode()+b'\n'
        await asyncio.Event().wait()

class Process:
    def __init__(self,lines):
        self.returncode=None;self.killed=False;self.stdin=Input();self.stdout=Output(lines)
    def kill(self):self.killed=True;self.returncode=-9
    async def wait(self):return self.returncode

def test_one_load_and_corrupt_error_keeps_model(monkeypatch):
    process=Process([{'ready':True},{'error':'ValueError'},{'result':{'predicted_label':'real'}},{'result':{'predicted_label':'fake'}}]);calls=[]
    async def create(*args,**kwargs):calls.append(args);return process
    monkeypatch.setattr(asyncio,'create_subprocess_exec',create)
    async def scenario():
        inference=worker.InferenceProcess()
        with pytest.raises(ValueError):await inference.predict('corrupt.mp4')
        assert not process.killed
        assert await inference.predict('valid.mp4')=={'predicted_label':'real'}
        assert await inference.predict('valid2.mp4')=={'predicted_label':'fake'}
        assert len(calls)==1
        await inference.close();assert process.killed
    asyncio.run(scenario())

def test_timeout_terminates_process(monkeypatch):
    process=Process([{'ready':True}])
    async def create(*args,**kwargs):return process
    monkeypatch.setattr(asyncio,'create_subprocess_exec',create)
    monkeypatch.setattr(worker,'INFERENCE_TIMEOUT_SECONDS',.01)
    async def scenario():
        inference=worker.InferenceProcess()
        with pytest.raises(TimeoutError):await inference.predict('slow.mp4')
        assert process.killed and inference.process is None
    asyncio.run(scenario())
