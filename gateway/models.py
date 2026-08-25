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
    prompt: str
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


class SessionCreateRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    conversation_url: str | None = Field(default=None, max_length=2048)
    profile_name: str = Field(default="default", min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")


class SessionUpdateRequest(BaseModel):
    conversation_url: str | None = Field(default=None, max_length=2048)
    profile_name: str | None = Field(default=None, min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    enabled: bool | None = None


class SessionResponse(BaseModel):
    session_id: str
    conversation_url: str | None
    profile_name: str
    enabled: bool
    created_at: str
    updated_at: str


class MemoryCreateRequest(BaseModel):
    content: str = Field(min_length=1, max_length=20_000)


class MemoryResponse(BaseModel):
    id: int
    session_id: str
    content: str
    created_at: str
