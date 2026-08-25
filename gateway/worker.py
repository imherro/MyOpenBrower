from __future__ import annotations

import asyncio
from contextlib import suppress
from uuid import uuid4

from gateway.config import Settings
from gateway.db import TaskRepository
from gateway.providers import ChatProvider, ProviderError, ProviderRequest


class Worker:
    def __init__(self, repository: TaskRepository, provider: ChatProvider, settings: Settings) -> None:
        self.repository = repository
        self.provider = provider
        self.settings = settings
        self.worker_id = f"worker-{uuid4().hex[:8]}"
        self._stopping = asyncio.Event()

    def stop(self) -> None:
        self._stopping.set()

    async def run(self) -> None:
        self.repository.recover_stale(self.settings.stale_task_seconds)
        while not self._stopping.is_set():
            task = self.repository.claim_next(self.worker_id)
            if task is None:
                with suppress(TimeoutError):
                    await asyncio.wait_for(self._stopping.wait(), timeout=self.settings.poll_interval_seconds)
                continue
            await self._execute(task)

    async def _execute(self, task: dict) -> None:
        heartbeat = asyncio.create_task(self._heartbeat_loop(task["task_id"]))
        try:
            answer = await self.provider.ask(ProviderRequest(
                task_id=task["task_id"], session_id=task["session_id"], prompt=task["prompt"],
                timeout_seconds=task["timeout_seconds"],
            ))
            self.repository.complete(task["task_id"], answer)
        except ProviderError as exc:
            if exc.code == "AUTH_REQUIRED":
                self.repository.mark_auth_required(task["task_id"], str(exc))
            else:
                retry_after = min(5 * (3 ** (task["attempt_count"] - 1)), 60) if exc.retryable else None
                self.repository.fail(task["task_id"], exc.code, str(exc), retry_after)
        except Exception as exc:
            self.repository.fail(task["task_id"], "INTERNAL_ERROR", str(exc)[:2000], retry_after_seconds=5)
        finally:
            heartbeat.cancel()
            with suppress(asyncio.CancelledError):
                await heartbeat

    async def _heartbeat_loop(self, task_id: str) -> None:
        while True:
            await asyncio.sleep(10)
            self.repository.heartbeat(task_id, self.worker_id)
