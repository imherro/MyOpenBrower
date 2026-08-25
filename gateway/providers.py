from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Protocol


class ProviderError(Exception):
    def __init__(self, code: str, message: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True)
class ProviderRequest:
    task_id: str
    session_id: str
    prompt: str
    timeout_seconds: int


class ChatProvider(Protocol):
    async def ask(self, request: ProviderRequest) -> str: ...


class DemoProvider:
    async def ask(self, request: ProviderRequest) -> str:
        return f"[demo:{request.session_id}] {request.prompt}"


class OpenBrowserProvider:
    """Bridge to a separately deployed OpenBrowser driver using a JSON stdin/stdout contract."""

    def __init__(self, command: str | None) -> None:
        self.command = command

    async def ask(self, request: ProviderRequest) -> str:
        if not self.command:
            raise ProviderError(
                "OPENBROWSER_NOT_CONFIGURED",
                "Set GATEWAY_OPENBROWSER_COMMAND to an OpenBrowser driver command.",
                retryable=False,
            )
        try:
            process = await asyncio.create_subprocess_shell(
                self.command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            payload = json.dumps({
                "task_id": request.task_id,
                "session_id": request.session_id,
                "prompt": request.prompt,
                "timeout_seconds": request.timeout_seconds,
            }).encode()
            stdout, stderr = await asyncio.wait_for(process.communicate(payload), timeout=request.timeout_seconds)
        except TimeoutError as exc:
            raise ProviderError("GENERATION_TIMEOUT", "OpenBrowser driver timed out.", retryable=True) from exc
        if process.returncode != 0:
            raise ProviderError("BROWSER_DRIVER_FAILED", stderr.decode(errors="replace")[:2000], retryable=True)
        try:
            response = json.loads(stdout)
            answer = response["answer"]
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise ProviderError("ANSWER_EXTRACTION_FAILED", "Driver stdout must contain JSON with an answer field.", retryable=True) from exc
        if not isinstance(answer, str) or not answer.strip():
            raise ProviderError("ANSWER_EXTRACTION_FAILED", "Driver returned an empty answer.", retryable=True)
        return answer


def build_provider(name: str, command: str | None) -> ChatProvider:
    if name == "demo":
        return DemoProvider()
    if name == "openbrowser":
        return OpenBrowserProvider(command)
    raise ValueError(f"Unsupported provider: {name}")
