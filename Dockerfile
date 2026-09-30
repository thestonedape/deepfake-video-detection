FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TORCH_NUM_THREADS=1 INFERENCE_BATCH_SIZE=1 PORT=8000
WORKDIR /app
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./
COPY best_model.pt ./best_model.pt
RUN useradd --create-home appuser && mkdir -p /app/storage && chown -R appuser:appuser /app
USER appuser
EXPOSE 8000
CMD ["python", "scripts/supervise.py"]
