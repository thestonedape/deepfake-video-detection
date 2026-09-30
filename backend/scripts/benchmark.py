"""Sequential real-model native video benchmark. No queue/provider claims."""
import argparse
import asyncio
import hashlib
import json
import sys
import tempfile
import threading
import time
from dataclasses import asdict
from pathlib import Path
import cv2
import numpy as np
import psutil

parser=argparse.ArgumentParser()
parser.add_argument('--runtime',choices=['baseline','worker'],required=True)
parser.add_argument('--requests',type=int,default=100)
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args();root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
peak=[0];done=threading.Event()
def sample():
    parent=psutil.Process()
    while not done.wait(.02):
        try: peak[0]=max(peak[0],sum(p.memory_info().rss for p in [parent]+parent.children(recursive=True)))
        except psutil.Error:pass
threading.Thread(target=sample,daemon=True).start()

async def run():
    started=time.perf_counter()
    if args.runtime=='baseline':
        from model import DeepfakeService
        service=DeepfakeService(root/'best_model.pt')
        async def infer(path):return asdict(service.predict_video(path))
    else:
        from worker import InferenceProcess
        service=InferenceProcess();await service.start()
        async def infer(path):return await service.predict(path)
    cold=time.perf_counter()-started
    with tempfile.TemporaryDirectory(prefix='deepfake-benchmark-') as directory:
        paths=[];rng=np.random.default_rng(7300930)
        for i in range(50):
            path=Path(directory)/f'{i:02}.avi'
            writer=cv2.VideoWriter(str(path),cv2.VideoWriter_fourcc(*'MJPG'),10,(64,64))
            if not writer.isOpened():raise RuntimeError('Fixture codec unavailable')
            for frame in range(10):writer.write(rng.integers(0,256,(64,64,3),dtype=np.uint8))
            writer.release();paths.append(path)
        hashes=[hashlib.sha256(p.read_bytes()).hexdigest() for p in paths]
        await infer(paths[0]);latencies=[];results=[];failures=[]
        for i in range(args.requests):
            started=time.perf_counter()
            try:results.append(await infer(paths[i%50]))
            except Exception as exc:failures.append({'request':i,'type':type(exc).__name__})
            latencies.append(time.perf_counter()-started)
    if args.runtime=='worker':await service.close()
    done.set()
    report={'runtime':args.runtime,'scope':'native Windows, sequential inference; worker includes IPC but not upload, database, Redis queue wait or cache','corpus':'50 deterministic synthetic 10-frame 64x64 MJPEG AVI videos, seed 7300930; engineering/numerical tests, not accuracy evidence','requests':args.requests,'cold_start_seconds':cold,'warm_p50_seconds':float(np.percentile(latencies,50)),'warm_p95_seconds':float(np.percentile(latencies,95)),'throughput_per_second':args.requests/sum(latencies),'peak_process_group_rss_bytes':peak[0],'failures':failures,'raw_latency_seconds':latencies,'results':results,'corpus_sha256':hashes,'model_sha256':hashlib.sha256((root/'best_model.pt').read_bytes()).hexdigest(),'container_memory':'not measured; summed native RSS can include shared pages'}
    args.output.parent.mkdir(exist_ok=True,parents=True);args.output.write_text(json.dumps(report,indent=2))
    print(json.dumps({k:v for k,v in report.items() if k not in {'raw_latency_seconds','results','corpus_sha256'}}))

asyncio.run(run())
