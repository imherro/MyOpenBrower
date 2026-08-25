from __future__ import annotations

from enum import StrEnum
from pydantic import BaseModel, Field


class TaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    RETRY_WAIT = "retry_wait"
    COMPLETED = "completed"
    FAILED = "failed"
    AUTH_REQUIRED = "auth_required"
    CANCELLED = "cancelled"


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    prompt: str = Field(min_length=1, max_length=100_000)
    timeout_seconds: int | None = Field(default=None, ge=1, le=900)


class TaskResponse(BaseModel):
    task_id: str
    session_id: str
    status: TaskStatus
    answer: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    attempt_count: int
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None


class CreateTaskResponse(BaseModel):
    task_id: str
    status: TaskStatus
    status_url: str
