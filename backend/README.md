# Backend

FastAPI service for deepfake video prediction.

## Run locally

```powershell
python -m uvicorn app:app --reload
```

## Deploy on Render

- Build command: `pip install -r requirements.txt`
- Start command: `uvicorn app:app --host 0.0.0.0 --port $PORT`
- Health check: `/health`

For the monorepo deployment, keep `best_model.pt` in the repository root.
`app.py` also supports a checkpoint beside itself when `backend/` is deployed
as a separate repository.
