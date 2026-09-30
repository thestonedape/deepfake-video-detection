"""Compare original PyTorch serving with bounded CPU cache settings on 50 fixed videos."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

SETTINGS = {'ONEDNN_PRIMITIVE_CACHE_CAPACITY': '0', 'DNNL_PRIMITIVE_CACHE_CAPACITY': '0', 'MALLOC_ARENA_MAX': '2'}
parser = argparse.ArgumentParser()
parser.add_argument('--child', choices=['default', 'bounded'])
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()

if args.child:
    import cv2
    import numpy as np
    import torch
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from model import DeepfakeService
    model_path = Path(__file__).resolve().parents[1] / 'best_model.pt'
    service = DeepfakeService(model_path)
    results, hashes = [], []
    rng = np.random.default_rng(7300930)
    with tempfile.TemporaryDirectory() as directory:
        for i in range(50):
            path = Path(directory) / f'{i:02}.avi'
            writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'MJPG'), 10, (64, 64))
            if not writer.isOpened():
                raise RuntimeError('Fixture codec unavailable')
            for _ in range(10):
                writer.write(rng.integers(0, 256, (64, 64, 3), dtype=np.uint8))
            writer.release()
            hashes.append(hashlib.sha256(path.read_bytes()).hexdigest())
            result = service.predict_video(path)
            results.append({'label': result.predicted_label, 'probabilities': result.probabilities})
    args.output.write_text(json.dumps({'results': results, 'corpus_sha256': hashes,
        'model_sha256': hashlib.sha256(model_path.read_bytes()).hexdigest(), 'torch_version': torch.__version__}))
else:
    with tempfile.TemporaryDirectory() as directory:
        reports = {}
        for mode in ['default', 'bounded']:
            env = os.environ.copy()
            for key in SETTINGS:
                env.pop(key, None)
            if mode == 'bounded':
                env.update(SETTINGS)
            env['TORCH_NUM_THREADS'] = '1'
            env['INFERENCE_BATCH_SIZE'] = '1'
            path = Path(directory) / f'{mode}.json'
            subprocess.run([sys.executable, __file__, '--child', mode, '--output', str(path)], env=env, check=True)
            reports[mode] = json.loads(path.read_text())
    left, right = reports['default'], reports['bounded']
    differences = [abs(a['probabilities'][label] - b['probabilities'][label])
                   for a, b in zip(left['results'], right['results']) for label in a['probabilities']]
    same_labels = sum(a['label'] == b['label'] for a, b in zip(left['results'], right['results']))
    report = {'scope': 'Numerical verification only, not accuracy evidence; original PyTorch runtime and weights retained',
              'corpus': '50 synthetic 10-frame 64x64 MJPEG AVI videos, NumPy seed 7300930',
              'runtime_settings': SETTINGS, 'model_sha256': left['model_sha256'], 'torch_version': left['torch_version'],
              'corpus_sha256': left['corpus_sha256'], 'inputs': 50, 'unchanged_labels': same_labels,
              'max_absolute_probability_difference': max(differences), 'results': reports,
              'passed': left['corpus_sha256'] == right['corpus_sha256'] and same_labels == 50 and max(differences) <= 0.001}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2))
    print(json.dumps({key: value for key, value in report.items() if key not in {'results', 'corpus_sha256'}}))
    if not report['passed']:
        raise SystemExit(1)
