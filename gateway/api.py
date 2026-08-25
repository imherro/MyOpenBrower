from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.responses import HTMLResponse

from gateway.config import Settings
from gateway.db import TaskRepository
from gateway.models import (ChatRequest, CreateTaskResponse, MemoryCreateRequest, MemoryResponse,
                            SessionCreateRequest, SessionResponse, SessionUpdateRequest, TaskResponse)
from gateway.providers import build_provider
from gateway.worker import Worker


def _task_response(task: dict) -> TaskResponse:
    return TaskResponse(
        task_id=task["task_id"], session_id=task["session_id"], prompt=task["prompt"], status=task["status"], answer=task["result"],
        error_code=task["error_code"], error_message=task["error_message"], attempt_count=task["attempt_count"],
        created_at=task["created_at"], started_at=task["started_at"], completed_at=task["completed_at"],
    )


def _session_response(session: dict) -> SessionResponse:
    return SessionResponse(
        session_id=session["session_id"], conversation_url=session["conversation_url"],
        profile_name=session["profile_name"], enabled=bool(session["enabled"]),
        created_at=session["created_at"], updated_at=session["updated_at"],
    )


def _memory_response(memory: dict) -> MemoryResponse:
    return MemoryResponse(id=memory["id"], session_id=memory["session_id"], content=memory["content"], created_at=memory["created_at"])


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or Settings.from_env()
    repository = TaskRepository(resolved.db_path)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        repository.initialize()
        worker_task: asyncio.Task | None = None
        worker: Worker | None = None
        if resolved.worker_enabled:
            worker = Worker(repository, build_provider(
                resolved.provider, resolved.openbrowser_command, base_url=resolved.chatgpt_base_url,
                profiles_dir=resolved.browser_profiles_dir, headless=resolved.browser_headless,
                executable=resolved.browser_executable, failure_dir=resolved.failure_dir,
            ), resolved)
            worker_task = asyncio.create_task(worker.run(), name="chat-gateway-worker")
        app.state.repository = repository
        yield
        if worker:
            worker.stop()
        if worker_task:
            await worker_task

    app = FastAPI(title="ChatGPT Web API Gateway", version="0.1.0", lifespan=lifespan)

    async def require_api_key(x_api_key: Annotated[str | None, Header()] = None) -> None:
        if resolved.api_key and x_api_key != resolved.api_key:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing X-API-Key")

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def test_console() -> str:
        return TEST_CONSOLE_HTML

    @app.get("/health/live")
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready")
    async def ready() -> dict[str, object]:
        return {"status": "ok", "provider": resolved.provider, "worker_enabled": resolved.worker_enabled}

    @app.post("/api/chat", response_model=CreateTaskResponse, status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(require_api_key)])
    async def create_task(body: ChatRequest, request: Request) -> CreateTaskResponse:
        task = repository.create_task(body.session_id, body.prompt, body.timeout_seconds or resolved.task_timeout_seconds)
        return CreateTaskResponse(task_id=task["task_id"], status=task["status"], status_url=str(request.url_for("get_task", task_id=task["task_id"])))

    @app.get("/api/tasks", response_model=list[TaskResponse], dependencies=[Depends(require_api_key)])
    async def list_tasks() -> list[TaskResponse]:
        return [_task_response(task) for task in repository.list_tasks()]

    @app.get("/api/tasks/{task_id}", response_model=TaskResponse, name="get_task", dependencies=[Depends(require_api_key)])
    async def get_task(task_id: str) -> TaskResponse:
        task = repository.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        return _task_response(task)

    @app.post("/api/tasks/{task_id}/cancel", response_model=TaskResponse, dependencies=[Depends(require_api_key)])
    async def cancel_task(task_id: str) -> TaskResponse:
        task = repository.cancel_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        if task["status"] not in {"cancelled"}:
            raise HTTPException(status_code=409, detail="Only pending or retry-wait tasks can be cancelled")
        return _task_response(task)

    @app.post("/api/tasks/{task_id}/retry", response_model=TaskResponse, dependencies=[Depends(require_api_key)])
    async def retry_task(task_id: str) -> TaskResponse:
        task = repository.retry_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        if task["status"] not in {"pending", "retry_wait"}:
            raise HTTPException(status_code=409, detail="Only failed or cancelled tasks can be retried")
        return _task_response(task)

    @app.get("/api/sessions", response_model=list[SessionResponse], dependencies=[Depends(require_api_key)])
    async def list_sessions() -> list[SessionResponse]:
        return [_session_response(item) for item in repository.list_sessions()]

    @app.post("/api/sessions", response_model=SessionResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_api_key)])
    async def create_session(body: SessionCreateRequest) -> SessionResponse:
        if repository.get_session(body.session_id):
            raise HTTPException(status_code=409, detail="Session already exists")
        return _session_response(repository.create_session(body.session_id, body.conversation_url, body.profile_name))

    @app.patch("/api/sessions/{session_id}", response_model=SessionResponse, dependencies=[Depends(require_api_key)])
    async def update_session(session_id: str, body: SessionUpdateRequest) -> SessionResponse:
        if body.conversation_url is None and body.profile_name is None and body.enabled is None:
            raise HTTPException(status_code=422, detail="At least one field is required")
        updated = repository.update_session(
            session_id, conversation_url=body.conversation_url, profile_name=body.profile_name, enabled=body.enabled,
            update_conversation="conversation_url" in body.model_fields_set,
        )
        if not updated:
            raise HTTPException(status_code=404, detail="Session not found")
        return _session_response(updated)

    @app.get("/api/sessions/{session_id}/memory", response_model=list[MemoryResponse], dependencies=[Depends(require_api_key)])
    async def list_memory(session_id: str) -> list[MemoryResponse]:
        if not repository.get_session(session_id):
            raise HTTPException(status_code=404, detail="Session not found")
        return [_memory_response(item) for item in repository.list_memory(session_id)]

    @app.post("/api/sessions/{session_id}/memory", response_model=MemoryResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_api_key)])
    async def add_memory(session_id: str, body: MemoryCreateRequest) -> MemoryResponse:
        try:
            return _memory_response(repository.add_memory(session_id, body.content))
        except KeyError:
            raise HTTPException(status_code=404, detail="Session not found") from None

    @app.delete("/api/sessions/{session_id}/memory/{memory_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_api_key)])
    async def delete_memory(session_id: str, memory_id: int) -> None:
        if not repository.delete_memory(session_id, memory_id):
            raise HTTPException(status_code=404, detail="Memory item not found")

    return app


TEST_CONSOLE_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>ChatGPT Web Gateway 测试控制台</title>
  <style>
    :root { color-scheme: dark; font-family: Inter, "Microsoft YaHei", sans-serif; }
    body { margin: 0; background: #10151f; color: #e6edf7; }
    main { max-width: 1500px; margin: 0 auto; padding: 24px; }
    h1 { margin: 0 0 6px; font-size: 24px; }
    .subtle { color: #9cacbf; margin: 0 0 24px; }
    form { display: grid; grid-template-columns: 180px 1fr auto; gap: 12px; align-items: start; margin-bottom: 20px; }
    input, textarea, button { box-sizing: border-box; border-radius: 8px; border: 1px solid #334155; background: #182131; color: inherit; font: inherit; }
    input, textarea { width: 100%; padding: 10px; }
    textarea { min-height: 72px; resize: vertical; }
    button { padding: 10px 16px; background: #2563eb; cursor: pointer; }
    button:hover { background: #1d4ed8; }
    .toolbar { display: flex; justify-content: space-between; gap: 12px; align-items: center; margin: 8px 0; }
    #message { color: #93c5fd; min-height: 20px; }
    .table-wrap { overflow-x: auto; border: 1px solid #2a3545; border-radius: 10px; }
    table { width: 100%; border-collapse: collapse; min-width: 1180px; }
    th, td { padding: 12px; text-align: left; vertical-align: top; border-bottom: 1px solid #2a3545; }
    th { color: #aebed1; background: #172033; position: sticky; top: 0; }
    td { font-size: 13px; white-space: pre-wrap; overflow-wrap: anywhere; }
    .task { font-family: ui-monospace, Consolas, monospace; color: #a5b4fc; }
    .status { display: inline-block; padding: 3px 7px; border-radius: 999px; background: #334155; font-size: 12px; }
    .completed { background: #166534; } .failed, .auth_required { background: #991b1b; }
    .pending, .retry_wait { background: #854d0e; } .running { background: #1d4ed8; }
    .empty { padding: 32px; text-align: center; color: #9cacbf; }
    @media (max-width: 720px) { form { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
  <main>
    <h1>ChatGPT Web Gateway 测试控制台</h1>
    <p class="subtle">提交测试问题、查看所有任务的状态与完整答案。页面每 2 秒自动刷新。</p>
    <form id="chat-form">
      <input id="session" name="session_id" value="general" maxlength="128" required aria-label="会话 ID">
      <textarea id="prompt" name="prompt" placeholder="输入测试问题…" required aria-label="问题"></textarea>
      <button type="submit">提交问题</button>
    </form>
    <div class="toolbar"><input id="api-key" type="password" placeholder="可选：X-API-Key" aria-label="API Key"><span id="message"></span><button id="refresh" type="button">立即刷新</button></div>
    <div class="table-wrap">
      <table>
        <thead><tr><th>状态</th><th>会话</th><th>问题</th><th>答案 / 错误</th><th>尝试</th><th>创建时间</th><th>完成时间</th><th>任务 ID</th></tr></thead>
        <tbody id="tasks"><tr><td class="empty" colspan="8">正在加载…</td></tr></tbody>
      </table>
    </div>
  </main>
  <script>
    const table = document.getElementById('tasks');
    const message = document.getElementById('message');
    function cell(row, value, className = '') {
      const element = document.createElement('td');
      if (className) element.className = className;
      element.textContent = value ?? '—';
      row.appendChild(element);
    }
    const apiKey = document.getElementById('api-key'); apiKey.value = localStorage.getItem('gateway_api_key') || '';
    apiKey.addEventListener('change', () => localStorage.setItem('gateway_api_key', apiKey.value));
    function headers() { return apiKey.value ? {'X-API-Key': apiKey.value} : {}; }
    function displayTime(value) { return value ? new Date(value).toLocaleString() : '—'; }
    async function loadTasks() {
      try {
        const response = await fetch('/api/tasks', {headers: headers()});
        if (!response.ok) throw new Error('无法读取任务列表');
        const tasks = await response.json();
        table.replaceChildren();
        if (!tasks.length) {
          const row = document.createElement('tr'); const empty = document.createElement('td');
          empty.colSpan = 8; empty.className = 'empty'; empty.textContent = '还没有任务。'; row.appendChild(empty); table.appendChild(row); return;
        }
        for (const task of tasks) {
          const row = document.createElement('tr');
          const state = document.createElement('td'); const badge = document.createElement('span');
          badge.className = `status ${task.status}`; badge.textContent = task.status; state.appendChild(badge); row.appendChild(state);
          cell(row, task.session_id); cell(row, task.prompt);
          cell(row, task.answer || (task.error_code ? `${task.error_code}: ${task.error_message || ''}` : '—'));
          cell(row, String(task.attempt_count)); cell(row, displayTime(task.created_at)); cell(row, displayTime(task.completed_at)); cell(row, task.task_id, 'task');
          table.appendChild(row);
        }
      } catch (error) { message.textContent = error.message; }
    }
    document.getElementById('chat-form').addEventListener('submit', async (event) => {
      event.preventDefault(); message.textContent = '正在创建任务…';
      const response = await fetch('/api/chat', { method: 'POST', headers: {...headers(), 'Content-Type': 'application/json'}, body: JSON.stringify({session_id: document.getElementById('session').value, prompt: document.getElementById('prompt').value}) });
      const result = await response.json();
      if (!response.ok) { message.textContent = result.detail ? JSON.stringify(result.detail) : '创建失败'; return; }
      message.textContent = `任务已创建：${result.task_id}`; document.getElementById('prompt').value = ''; loadTasks();
    });
    document.getElementById('refresh').addEventListener('click', loadTasks);
    loadTasks(); setInterval(loadTasks, 2000);
  </script>
</body>
</html>"""
