# Backend

FastAPI + PostgreSQL + Redis/arq asynchronous video inference service. The authoritative setup, API, failure handling, benchmarks and deployment status are in the [root README](../README.md).

## Run locally

```powershell
python scripts/migrate.py
python scripts/supervise.py
```

## Deploy on Render

- Build command: `pip install -r requirements.txt`
- Start command: `python scripts/supervise.py`
- Health check: `/health`

For the monorepo deployment, keep `best_model.pt` in the repository root.
`app.py` also supports a checkpoint beside itself when `backend/` is deployed
as a separate repository.

The API requires a separate arq worker. Starting only uvicorn does not serve jobs. Use the root Dockerfile for the single-service free deployment and retain its verified CPU settings; Docker Compose separates API/worker locally.
