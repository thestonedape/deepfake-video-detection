"""Durable job API. Redis dispatch can fail without losing accepted work."""
import hashlib
import os
import secrets
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Text, DateTime, Integer, Boolean, JSON, select, func, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

class Base(DeclarativeBase):
    pass

class Job(Base):
    __tablename__ = 'deepfake_jobs'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64))
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    object_key: Mapped[str] = mapped_column(Text)
    filename: Mapped[str] = mapped_column(String(255))
    version: Mapped[str] = mapped_column(String(100), index=True)
    status: Mapped[str] = mapped_column(String(16), index=True, default='queued')
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(String(100), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    lease: Mapped[str | None] = mapped_column(String(36), nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cleanup_pending: Mapped[bool] = mapped_column(Boolean, default=True)

engine = create_async_engine(os.getenv('DATABASE_URL','postgresql+asyncpg://postgres:postgres@localhost:5434/deepfake'), pool_pre_ping=True)
Session = async_sessionmaker(engine, expire_on_commit=False)
VERSION = os.getenv('MODEL_VERSION','torch-v1') + ':' + os.getenv('PREPROCESSING_VERSION','frames10-fft-v1')

def token_digest(token):
    return hashlib.sha256(token.encode()).hexdigest()

def public_job(job):
    return {'job_id':job.id,'status':job.status,'result':job.result if job.status=='completed' else None,'error':job.error if job.status=='failed' else None,'model_version':job.version}
