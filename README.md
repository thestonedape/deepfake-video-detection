# Deepfake Video Detection

[![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=white)](frontend/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)](backend/)
[![PyTorch](https://img.shields.io/badge/PyTorch-2.6-EE4C2C?logo=pytorch&logoColor=white)](backend/model.py)
[![Vercel](https://img.shields.io/badge/Frontend-Vercel-black?logo=vercel)](https://deepfake-ten-psi.vercel.app)
[![Render](https://img.shields.io/badge/API-Render-46E3B7?logo=render&logoColor=white)](https://deepfake-video-detection-486r.onrender.com/health)

A full-stack deepfake video detection system that combines spatial features from
EfficientNet-B4 with handcrafted frequency-domain features. The web interface
uploads a video to a FastAPI service, which samples frames, runs CPU inference,
and returns a video-level real/fake prediction with confidence scores.

## Live links

- **Frontend:** [deepfake-ten-psi.vercel.app](https://deepfake-ten-psi.vercel.app)
- **Backend health:** [deepfake-video-detection-486r.onrender.com/health](https://deepfake-video-detection-486r.onrender.com/health)
- **Interactive API docs:** [deepfake-video-detection-486r.onrender.com/docs](https://deepfake-video-detection-486r.onrender.com/docs)

> Render's free instance can sleep when idle. The first request after inactivity
> may take longer while the backend starts.

## Features

- Upload and preview MP4, MOV, WEBM, AVI, or MKV videos
- Validate extensions and reject uploads larger than 100 MB
- Sample 10 frames across each video without retaining the full video in memory
- Fall back to sequential decoding when a codec does not support random seeking
- Combine spatial and frequency-domain representations for classification
- Average frame probabilities into a video-level verdict
- Display confidence, class probabilities, frames read, and frames sampled
- Run CPU-only inference for compatibility with Render's free tier
- Serve a responsive Indigo Dashboard frontend with explicit cache controls

## System flow

```mermaid
flowchart LR
    A[Video upload] --> B[FastAPI validation]
    B --> C[OpenCV frame sampling]
    C --> D[224 x 224 preprocessing]
    D --> E[EfficientNet-B4 spatial branch]
    D --> F[24D frequency features]
    F --> G[Frequency MLP]
    E --> H[2816D fused representation]
    G --> H
    H --> I[Frame probabilities]
    I --> J[Video-level average]
    J --> K[Real or fake result]
```

## Model architecture

| Component | Implementation |
|---|---|
| Input | 10 sampled RGB frames resized to 224 x 224 |
| Spatial branch | EfficientNet-B4 feature encoder |
| Spatial representation | 1792 dimensions |
| Frequency input | 8 radial FFT bins + 16 pooled grayscale values |
| Frequency MLP | 24 → 512 → 1024 |
| Fusion | 1792 + 1024 = 2816 dimensions |
| Classifier | 2816 → 1024 → 512 → 256 → 2 |
| Output labels | `fake`, `real` |
| Video prediction | Mean probability across sampled frames |

## Technology stack

| Layer | Technologies |
|---|---|
| Frontend | React 19, TypeScript, Vite |
| Backend | FastAPI, Uvicorn, Python |
| Machine learning | PyTorch, Torchvision, EfficientNet-B4 |
| Video processing | OpenCV, NumPy |
| Frontend hosting | Vercel |
| Backend hosting | Render |
| Model storage | Git Large File Storage |

## Repository structure

```text
deepfake-video-detection/
├── frontend/                   React and TypeScript web application
│   ├── src/App.tsx             Upload and prediction interface
│   ├── src/theme.ts            Material UI theme configuration
│   └── vercel.json             SPA routing and cache headers
├── backend/                    FastAPI inference service
│   ├── app.py                  API routes, CORS, and upload validation
│   ├── model.py                Model architecture and video inference
│   ├── requirements.txt        Pinned CPU dependencies
│   └── render.yaml             Standalone Render configuration
├── best_model.pt               Git LFS checkpoint
├── render.yaml                 Monorepo Render configuration
├── vercel.json                 Monorepo Vercel configuration
└── deepfake_video_training_kaggle.ipynb
```

## Asynchronous job architecture

Inference on a 512 MB free instance is memory-bound, so request handling is separated from inference: the API accepts and persists work, and a single worker runs the model.

```mermaid
flowchart LR
    U[React client] -->|POST /jobs| A[FastAPI: stream + validate + hash]
    A -->|cache hit| P[(PostgreSQL job ledger)]
    A -->|commit job, then enqueue| P
    A --> S[Private object storage]
    A -->|fast path| R[(Redis: deepfake queue)]
    P -->|reconcile every 15 s| R
    R --> W[arq worker, 1 active job]
    W -->|stdin/stdout| C[Inference subprocess: model loaded once]
    W --> P
    U -->|GET /jobs/id + X-Job-Token, backoff polling| A
```

- **Durable ledger.** PostgreSQL owns job state. After commit the API enqueues immediately; if Redis is down, a reconcile loop re-dispatches committed jobs. Redis is disposable.
- **Bounded resources.** One active inference, a bounded queue (`MAX_QUEUED_JOBS`, default 20) with `429 Retry-After` beyond it, and the unchanged 100 MB upload ceiling.
- **Validation before expensive work.** Extension, MIME and extension/MIME agreement, container signature and streamed size are checked on upload. The inference child checks decodability, resolution (≤ 3840×2160), frame count (≤ 18,000) and duration (≤ 10 min) before sampling frames.
- **Killable inference.** The model runs in a supervised subprocess. A timeout (`INFERENCE_TIMEOUT_SECONDS`, default 300) kills the whole process and reclaims its memory; the next job starts a fresh child. On Linux the child dies with its parent.
- **Retries by failure class.** Storage/network errors (transport errors, 429, 5xx) retry at most 3 times with 5 s / 20 s backoff. Corrupt media and deterministic model errors fail once.
- **Leases.** Workers hold a 60 s lease renewed every 10 s. Expired leases are recovered, and a worker that lost its lease cannot publish results.
- **Cleanup.** Per-job scratch directories are removed after success, failure, cancellation and on worker restart. Stored originals are deleted after a terminal result, with reconciliation retrying failed deletions.
- **Result cache.** Keyed by content SHA-256 + model version + preprocessing version. Each caller still gets its own job and capability token.
- **Anonymous access control.** Each job returns an opaque `job_token`; only its SHA-256 is stored. A wrong or missing token returns 404, the same as a missing job.
- **Memory.** The model is built on PyTorch's `meta` device and adopts memory-mapped checkpoint tensors (`MODEL_LOAD_MODE=mmap`, default). Weights stay file-backed instead of occupying two anonymous heap copies. Outputs are bit-identical to the previous loader on the benchmark corpus.

The existing frame sampling, frequency features, label mapping and codec-seeking fallback are unchanged.

## API

| Route | Behavior |
|---|---|
| `POST /jobs` | multipart `file` → `202 {job_id, job_token, status, cached, result?, model_version}`; 413 over 100 MB, 415 type/MIME mismatch, 422 bad signature/empty, 429 queue full, 503 persistence unavailable |
| `GET /jobs/{id}` | header `X-Job-Token`; returns `queued / processing / completed / failed` with `result` or `error` |
| `POST /predict` | compatibility endpoint on the same bounded worker (never a second model); waits up to 30 s, then returns the `202` job |
| `GET /health` | process liveness |
| `GET /ready` | database, Redis, storage configuration and a live worker heartbeat with the model loaded; otherwise 503 |
| `GET /metrics` | request, error and latency counters; JSON logs carry request IDs |

Completed result (unchanged fields):

```json
{
  "predicted_label": "fake",
  "confidence": 0.91,
  "probabilities": {"fake": 0.91, "real": 0.09},
  "frame_count": 284,
  "sampled_frames": 10
}
```

The frontend submits to `/jobs`, polls with exponential backoff, and shows a cold-start message while a sleeping free instance wakes.

## Verification and measured results

`cd backend && python -m pytest tests -q` runs 9 tests. With `SDE_TEST_DATABASE_URL` pointing to a disposable `*_test` database and Redis, this includes real PostgreSQL/Redis scenarios:

- valid, mismatched-type, bad-signature and oversized uploads
- queue saturation (429)
- capability-token enforcement
- worker cancellation and lease recovery, plus duplicate delivery
- result cache hits
- inference timeouts that kill the child process
- a corrupt video that fails without unloading the model
- storage outage retry and backoff up to the attempt limit
- no retry for corrupt media
- scratch cleanup

**512 MB container** (`backend/scripts/container_bench.py`). This is the single supervised API+worker container, as deployed on a free web service, run under Docker Desktop (WSL2) with a hard 512 MB limit and no swap. It uses the real model and 100 submissions: 50 distinct synthetic 10-frame videos, then the same 50 again (cache hits). Synthetic media exercises serving only; it is not accuracy evidence.

| 100 jobs, 4 clients, 512 MB | Before tuning | After (mmap load + 0.5 s poll) |
|---|---:|---:|
| Completed | 100 / 100 | 100 / 100 |
| Upload acknowledgement p50 / p95 | 32 / 47 ms | 38 / 55 ms |
| Fresh job end-to-end p50 / p95 (incl. queue wait) | 29.3 / 32.4 s | **8.2 / 8.3 s** |
| Cache-hit end-to-end p50 | 26 ms | 35 ms |
| Completed jobs/s | 0.25 | **0.93** |
| Peak anonymous memory | 470 MiB | **356 MiB** |
| Cold start to `/ready` | 7.8 s | 6.3 s |
| OOM kills | 0 | 0 |

In the "before" column, the single-slot worker idled up to 5 s (arq `poll_delay`) between jobs, and the inference child held both randomly initialized and loaded weights in anonymous memory. Saturation with 30 concurrent clients (`artifacts/container-512m-saturation.json`) produced 85 `429 Retry-After` responses. All 100 jobs completed after client retries, memory stayed at 353 MiB, and there were no OOM kills. `memory.peak` reaches the 512 MiB limit in every run because reclaimable page cache counts towards it. The image is 2.71 GB uncompressed.

**Native sequential inference** (Windows, same 50-video corpus, 100 requests; `backend/scripts/benchmark.py`):

| | Original in-process | Worker subprocess (mmap) |
|---|---:|---:|
| Warm p50 / p95 | 1.63 / 1.83 s | 1.24 / 1.32 s |
| Inferences/s | 0.60 | 0.80 |
| Results vs original | — | identical on all 100 |

**ONNX export** was tested and **not adopted**. The 50 frame-level labels were unchanged, but the maximum probability difference was 0.226, far above the 0.001 gate (`artifacts/onnx-verification.json`). PyTorch remains the runtime.

## Local development

### Prerequisites

- Python 3.11
- Node.js 20 or newer
- Git LFS

Clone the repository and download the checkpoint:

```powershell
git clone https://github.com/thestonedape/deepfake-video-detection.git
cd deepfake-video-detection
git lfs install
git lfs pull
```

### Run the backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m uvicorn app:app --reload
```

The API is available at `http://127.0.0.1:8000`.

### Run the frontend

```powershell
cd frontend
npm install
npm run dev
```

Create `frontend/.env.local` when using a different backend:

```text
VITE_API_URL=http://127.0.0.1:8000
```

## Deployment

### Render backend variables

```text
PYTHON_VERSION=3.11.11
FRONTEND_ORIGINS=https://deepfake-ten-psi.vercel.app
TORCH_NUM_THREADS=1
INFERENCE_BATCH_SIZE=1
```

Build command:

```text
pip install -r backend/requirements.txt
```

Start command:

```text
cd backend && uvicorn app:app --host 0.0.0.0 --port $PORT
```

The upgraded service is deployed from the root `Dockerfile`. `scripts/supervise.py` runs the API and one arq worker in one container, because the free tier has no separate worker service. It also needs `DATABASE_URL` (PostgreSQL), `REDIS_URL` (native `rediss://` TLS URL), `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` and a private `SUPABASE_VIDEO_BUCKET`. `docker compose up --build` runs PostgreSQL, Redis, migrations, API and worker locally. CI (`.github/workflows/verify.yml`) runs the tests against real PostgreSQL/Redis, builds the frontend and the Docker image, and triggers `RENDER_DEPLOY_HOOK` only on a passing `main` build. Free instances sleep: jobs survive restarts, but uninterrupted availability is not promised.

### Vercel frontend variable

```text
VITE_API_URL=https://deepfake-video-detection-486r.onrender.com
```

See [DEPLOYMENT.md](DEPLOYMENT.md), [BACKEND_DEPLOYMENT.md](BACKEND_DEPLOYMENT.md),
and [FRONTEND_DEPLOYMENT.md](FRONTEND_DEPLOYMENT.md) for additional details.
