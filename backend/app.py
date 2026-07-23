from __future__ import annotations

import os
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

try:
    from .model import DeepfakeService
except ImportError:
    from model import DeepfakeService
BACKEND_DIR = Path(__file__).resolve().parent
MODEL_PATH = BACKEND_DIR / "best_model.pt"
if not MODEL_PATH.exists():
    MODEL_PATH = BACKEND_DIR.parent / "best_model.pt"

DEFAULT_FRONTEND_ORIGINS = (
    "https://deepfake-ten-psi.vercel.app,"
    "http://localhost:5173,"
    "http://127.0.0.1:5173"
)
FRONTEND_ORIGINS = [
    origin.strip().rstrip("/")
    for origin in os.getenv("FRONTEND_ORIGINS", DEFAULT_FRONTEND_ORIGINS).split(",")
    if origin.strip()
]
MAX_UPLOAD_BYTES = 100 * 1024 * 1024
ALLOWED_EXTENSIONS = {".mp4", ".mov", ".webm", ".avi", ".mkv"}

app = FastAPI(title="Deepfake Detector API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)

service = DeepfakeService(MODEL_PATH)


@app.get("/")
def root():
    return {"name": "Deepfake Detector API", "status": "ok"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/predict")
def predict(file: UploadFile = File(...)):
    temp_path: Path | None = None

    try:
        if not file.filename:
            raise HTTPException(status_code=400, detail="A video file is required.")

        suffix = Path(file.filename).suffix.lower() or ".mp4"
        if suffix not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: {suffix}",
            )

        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_path = Path(temp_file.name)
            written = 0
            while chunk := file.file.read(1024 * 1024):
                written += len(chunk)
                if written > MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail="File exceeds 100 MB limit.",
                    )
                temp_file.write(chunk)

        result = service.predict_video(temp_path)
        return {
            "filename": file.filename,
            "predicted_label": result.predicted_label,
            "confidence": result.confidence,
            "probabilities": result.probabilities,
            "frame_count": result.frame_count,
            "sampled_frames": result.sampled_frames,
        }
    except HTTPException:
        raise
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Inference failed.") from exc
    finally:
        file.file.close()
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
