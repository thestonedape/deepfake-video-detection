> Upgrade rollout is pending. Use the root Dockerfile with the API/worker supervisor, PostgreSQL, native TLS Redis and private Supabase storage as documented in [README](README.md#deployment). The verified bounded CPU cache settings pass the 100-request synthetic memory gate; see the README for exact scope and required deployment settings. The legacy instructions below describe the previous synchronous service only. Preserve that revision for rollback. Push this repository only through its `thestonedape` remote; the other remote must never receive changes.

# Backend Deployment

Deploy the FastAPI app on a CPU-only Render Python web service. The production
frontend origin is `https://deepfake-ten-psi.vercel.app`.

## Render settings

- Build command: `pip install -r backend/requirements.txt`
- Start command: `cd backend && uvicorn app:app --host 0.0.0.0 --port $PORT`
- Health check path: `/health`
- Instance type: `Free`
- Environment variable: `FRONTEND_ORIGINS=https://deepfake-ten-psi.vercel.app`
- Environment variable: `TORCH_NUM_THREADS=1`
- Environment variable: `INFERENCE_BATCH_SIZE=1`

## Required files

- The backend code stays in [backend/app.py](backend/app.py) and [backend/model.py](backend/model.py).
- The model checkpoint stays at [best_model.pt](best_model.pt) in the repo root.
- Track the checkpoint with Git LFS before pushing the repository.

## Git LFS

Run these commands from the repository root:

```powershell
git lfs install
git lfs track "best_model.pt"
git add .gitattributes .gitignore best_model.pt
git commit -m "Track model checkpoint with Git LFS"
git push origin main
```

Verify the checkpoint is tracked:

```powershell
git lfs ls-files
```

If `best_model.pt` was already committed as a normal Git object, first move the
existing history to LFS:

```powershell
git lfs migrate import --include="best_model.pt" --everything
git push --force-with-lease origin main
```

History migration rewrites commit IDs. Only use it when you understand the
impact on collaborators and protected branches.

## Local run

- `cd backend && python -m uvicorn app:app --reload`

## Connect the Vercel frontend

After Render gives you a backend URL, set this Vercel environment variable and
redeploy the frontend:

```text
VITE_API_URL=https://your-service-name.onrender.com
```
