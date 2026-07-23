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

Keep `best_model.pt` in this folder next to `app.py` when you push this folder to GitHub as a separate repository.
