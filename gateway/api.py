from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import asdict

from fastapi import FastAPI, HTTPException, Request, status

from gateway.config import Settings
from gateway.db import TaskRepository
from gateway.models import ChatRequest, CreateTaskResponse, TaskResponse
from gateway.providers import build_provider
from gateway.worker import Worker


def _task_response(task: dict) -> TaskResponse:
    return TaskResponse(
        task_id=task["task_id"], session_id=task["session_id"], status=task["status"], answer=task["result"],
        error_code=task["error_code"], error_message=task["error_message"], attempt_count=task["attempt_count"],
        created_at=task["created_at"], started_at=task["started_at"], completed_at=task["completed_at"],
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or Settings.from_env()
    repository = TaskRepository(resolved.db_path)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        repository.initialize()
        worker_task: asyncio.Task | None = None
        worker: Worker | None = None
        if resolved.worker_enabled:
            worker = Worker(repository, build_provider(resolved.provider, resolved.openbrowser_command), resolved)
            worker_task = asyncio.create_task(worker.run(), name="chat-gateway-worker")
        app.state.repository = repository
        yield
        if worker:
            worker.stop()
        if worker_task:
            await worker_task

    app = FastAPI(title="ChatGPT Web API Gateway", version="0.1.0", lifespan=lifespan)

    @app.get("/health/live")
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready")
    async def ready() -> dict[str, object]:
        return {"status": "ok", "provider": resolved.provider, "worker_enabled": resolved.worker_enabled}

    @app.post("/api/chat", response_model=CreateTaskResponse, status_code=status.HTTP_202_ACCEPTED)
    async def create_task(body: ChatRequest, request: Request) -> CreateTaskResponse:
        task = repository.create_task(body.session_id, body.prompt, body.timeout_seconds or resolved.task_timeout_seconds)
        return CreateTaskResponse(task_id=task["task_id"], status=task["status"], status_url=str(request.url_for("get_task", task_id=task["task_id"])))

    @app.get("/api/tasks/{task_id}", response_model=TaskResponse, name="get_task")
    async def get_task(task_id: str) -> TaskResponse:
        task = repository.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        return _task_response(task)

    return app
