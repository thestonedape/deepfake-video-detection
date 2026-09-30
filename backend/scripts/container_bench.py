"""Memory-limited async-job benchmark for the supervised API+worker container.

Requires disposable PostgreSQL/Redis reachable from the container, e.g.
    python scripts/container_bench.py --image sde/deepfake:upgrade --memory 512m \
        --database-url postgresql+asyncpg://postgres:postgres@host.docker.internal:55432/deepfake_bench \
        --redis-url redis://host.docker.internal:56379/2 --output ../artifacts/container-512m.json

The first 50 submissions are distinct synthetic videos; the next 50 repeat them (cache hits).
Synthetic media exercises the serving path only and is not accuracy evidence.
"""
import argparse
import json
import subprocess
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import cv2
import httpx
import numpy as np

parser = argparse.ArgumentParser()
parser.add_argument('--image', required=True)
parser.add_argument('--memory', default='512m')
parser.add_argument('--requests', type=int, default=100)
parser.add_argument('--concurrency', type=int, default=4)
parser.add_argument('--port', type=int, default=8011)
parser.add_argument('--database-url', required=True)
parser.add_argument('--redis-url', required=True)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--env', action='append', default=[], help='Additional non-secret runtime NAME=value settings')
args = parser.parse_args()
if not args.database_url.rsplit('/', 1)[-1].endswith(('_test', '_bench')):
    raise SystemExit('benchmark requires a disposable *_test or *_bench database')
name = f'deepfake-bench-{args.port}'


def docker(*cmd, check=True):
    return subprocess.run(['docker', *cmd], capture_output=True, text=True, check=check).stdout.strip()


def cgroup(file):
    try:
        return docker('exec', name, 'cat', f'/sys/fs/cgroup/{file}')
    except subprocess.CalledProcessError:
        return ''


env = ['-e', f'DATABASE_URL={args.database_url}', '-e', f'REDIS_URL={args.redis_url}', '-e', 'ENVIRONMENT=development',
       '-e', 'LOCAL_STORAGE_DIR=/app/storage', '-e', 'MAX_QUEUED_JOBS=20']
for setting in args.env:
    if '=' not in setting or setting.split('=', 1)[0] not in {
        'ONEDNN_PRIMITIVE_CACHE_CAPACITY', 'DNNL_PRIMITIVE_CACHE_CAPACITY', 'MALLOC_ARENA_MAX'
    }:
        raise SystemExit('Only supported non-secret resource settings may be benchmarked')
    env.extend(['-e', setting])
subprocess.run(['docker', 'run', '--rm', *env, args.image, 'python', 'scripts/migrate.py'], check=True, capture_output=True)
docker('rm', '-f', name, check=False)
started = time.perf_counter()
docker('run', '-d', '--name', name, '--memory', args.memory, '--memory-swap', args.memory, '-p', f'{args.port}:8000', *env, args.image)
base = f'http://127.0.0.1:{args.port}'
samples, anon, done = [], [], threading.Event()


def sample():
    while not done.wait(0.5):
        value = cgroup('memory.current')
        if value.isdigit():
            samples.append(int(value))
        stat = dict(line.split() for line in cgroup('memory.stat').splitlines()[:40] if line)
        if 'anon' in stat:
            anon.append(int(stat['anon']))  # non-reclaimable; page cache is excluded


threading.Thread(target=sample, daemon=True).start()
cold = None
with tempfile.TemporaryDirectory(prefix='deepfake-bench-') as folder, httpx.Client(timeout=120) as client:
    rng, videos = np.random.default_rng(7300930), []
    for i in range(50):
        path = Path(folder) / f'{i:02}.avi'
        writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'MJPG'), 10, (64, 64))
        for _ in range(10):
            writer.write(rng.integers(0, 256, (64, 64, 3), dtype=np.uint8))
        writer.release()
        videos.append(path.read_bytes())
    while time.perf_counter() - started < 600:
        if docker('inspect', '-f', '{{.State.Running}}', name, check=False) != 'true':
            break
        try:
            if client.get(base + '/ready').status_code == 200:
                cold = time.perf_counter() - started
                break
        except httpx.HTTPError:
            pass
        time.sleep(0.5)

    def submit(i):
        submitted, backpressure = time.perf_counter(), 0
        while True:
            t = time.perf_counter()
            try:
                r = client.post(base + '/jobs', files={'file': (f'{i % 50:02}.avi', videos[i % 50], 'video/x-msvideo')})
            except httpx.HTTPError as exc:
                return {'request': i, 'outcome': type(exc).__name__}
            if r.status_code == 429:
                backpressure += 1
                time.sleep(float(r.headers.get('Retry-After', '5')))
                continue
            ack = time.perf_counter() - t
            if r.status_code != 202:
                return {'request': i, 'outcome': f'http_{r.status_code}', 'ack_seconds': ack}
            body, delay = r.json(), 0.25
            while body['status'] not in {'completed', 'failed'} and time.perf_counter() - submitted < 900:
                time.sleep(delay)
                delay = min(delay * 1.5, 3)
                body = client.get(base + '/jobs/' + body['job_id'], headers={'X-Job-Token': r.json()['job_token']}).json()
            return {'request': i, 'outcome': body['status'], 'cached': r.json()['cached'], 'ack_seconds': ack,
                    'end_to_end_seconds': time.perf_counter() - submitted, 'backpressure_429s': backpressure,
                    'label': (body.get('result') or {}).get('predicted_label')}

    results = []
    if cold is not None:
        burst = time.perf_counter()
        with ThreadPoolExecutor(args.concurrency) as pool:
            results = list(pool.map(submit, range(args.requests)))
        duration = time.perf_counter() - burst
done.set()
events = dict(line.split() for line in cgroup('memory.events').splitlines() if line)
peak = cgroup('memory.peak')
state = json.loads(docker('inspect', '-f', '{{json .State}}', name))
image_bytes = int(docker('image', 'inspect', '-f', '{{.Size}}', args.image))
logs = subprocess.run(['docker', 'logs', '--tail', '20', name], capture_output=True, text=True, encoding='utf-8', errors='replace')
docker('rm', '-f', name, check=False)


def pct(values, q):
    return float(np.percentile(values, q)) if values else None


fresh = [x for x in results if x.get('outcome') == 'completed' and not x['cached']]
hits = [x for x in results if x.get('outcome') == 'completed' and x['cached']]
report = {
    'scope': f'Docker Desktop (WSL2), one supervised API+arq worker container, --memory {args.memory} no swap; '
             'real model; local storage; synthetic 10-frame 64x64 MJPEG videos (not accuracy evidence)',
    'image': args.image, 'image_bytes': image_bytes, 'memory_limit': args.memory,
    'runtime_settings': args.env,
    'cold_start_to_ready_seconds': cold, 'requests': len(results), 'client_concurrency': args.concurrency,
    'outcomes': {o: sum(x['outcome'] == o for x in results) for o in {x['outcome'] for x in results}},
    'backpressure_429_responses': sum(x.get('backpressure_429s', 0) for x in results),
    'upload_ack_p50_seconds': pct([x['ack_seconds'] for x in results if 'ack_seconds' in x], 50),
    'upload_ack_p95_seconds': pct([x['ack_seconds'] for x in results if 'ack_seconds' in x], 95),
    'fresh_jobs': len(fresh),
    'fresh_end_to_end_p50_seconds': pct([x['end_to_end_seconds'] for x in fresh], 50),
    'fresh_end_to_end_p95_seconds': pct([x['end_to_end_seconds'] for x in fresh], 95),
    'cache_hits': len(hits),
    'cache_hit_end_to_end_p50_seconds': pct([x['end_to_end_seconds'] for x in hits], 50),
    'completed_jobs_per_second': (len(fresh) + len(hits)) / duration if results else 0,
    'peak_cgroup_memory_bytes': int(peak) if peak.isdigit() else (max(samples) if samples else None),
    'peak_anon_memory_bytes_sampled': max(anon) if anon else None,
    'peak_source': 'memory.peak' if peak.isdigit() else 'sampled memory.current',
    'oom_kill_events': int(events.get('oom_kill', 0)) if events else None,
    'container_oom_killed': state.get('OOMKilled'), 'container_exit_code': state.get('ExitCode'),
    'raw_requests': results,
}
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps(report, indent=2))
print(json.dumps({k: v for k, v in report.items() if k != 'raw_requests'}, indent=2))
if cold is None:
    print(logs.stdout[-2000:], logs.stderr[-2000:])
