"""Persistent child: one model load, killable whole-process inference timeout."""
import json
import sys
import os
import signal
import hashlib
from pathlib import Path
if sys.platform == 'linux':
    # Container worker death must also reclaim its model child and memory.
    import ctypes
    parent = os.getppid()
    ctypes.CDLL(None).prctl(1, signal.SIGKILL)
    if os.getppid() != parent: os.kill(os.getpid(), signal.SIGKILL)
from model import DeepfakeService
model_path=Path(__file__).parent/'best_model.pt'
with model_path.open('rb') as checkpoint:
    checksum=hashlib.file_digest(checkpoint,'sha256').hexdigest()
if os.getenv('MODEL_SHA256') and os.getenv('MODEL_SHA256') != checksum:
    raise RuntimeError('Model checksum mismatch')
service=DeepfakeService(model_path)
print(json.dumps({'ready':True}),flush=True)
for line in sys.stdin:
    try:
        path=Path(json.loads(line)['path'])
        import cv2
        video=cv2.VideoCapture(str(path))
        try:
            width=video.get(cv2.CAP_PROP_FRAME_WIDTH);height=video.get(cv2.CAP_PROP_FRAME_HEIGHT)
            frames=video.get(cv2.CAP_PROP_FRAME_COUNT);fps=video.get(cv2.CAP_PROP_FPS)
            if not video.isOpened() or min(width,height)<=0 or width*height>3840*2160 or frames>18000 or fps<=0 or frames/fps>600:
                raise ValueError('Unsupported video dimensions, length or codec')
        finally: video.release()
        result=service.predict_video(path)
        print(json.dumps({'result':{'predicted_label':result.predicted_label,'confidence':result.confidence,'probabilities':result.probabilities,'frame_count':result.frame_count,'sampled_frames':result.sampled_frames}}),flush=True)
    except Exception as exc:
        print(json.dumps({'error':type(exc).__name__}),flush=True)
