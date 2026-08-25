from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import async_playwright


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
    conversation_url: str | None = None
    profile_name: str = "default"
    memory_context: str = ""


@dataclass(frozen=True)
class ProviderResult:
    answer: str
    conversation_url: str | None = None


class ChatProvider(Protocol):
    async def ask(self, request: ProviderRequest) -> ProviderResult: ...


class DemoProvider:
    async def ask(self, request: ProviderRequest) -> ProviderResult:
        return ProviderResult(answer=f"[demo:{request.session_id}] {request.prompt}", conversation_url=request.conversation_url)


class CommandProvider:
    """Bridge to a separately deployed OpenBrowser driver using a JSON stdin/stdout contract."""

    def __init__(self, command: str | None) -> None:
        self.command = command

    async def ask(self, request: ProviderRequest) -> ProviderResult:
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
        return ProviderResult(answer=answer, conversation_url=response.get("conversation_url"))


class OpenBrowserProvider:
    """Persistent Chrome-profile adapter implemented with Playwright browser automation."""

    def __init__(self, base_url: str, profiles_dir: Path, headless: bool, executable: Path | None) -> None:
        self.base_url = base_url
        self.profiles_dir = profiles_dir
        self.headless = headless
        self.executable = executable

    async def ask(self, request: ProviderRequest) -> ProviderResult:
        profile_dir = self.profiles_dir / request.profile_name
        profile_dir.mkdir(parents=True, exist_ok=True)
        target_url = request.conversation_url or self.base_url
        composed_prompt = request.prompt
        if request.memory_context:
            composed_prompt = f"以下是本次会话的长期背景记忆，请在回答时参考：\n{request.memory_context}\n\n用户问题：\n{request.prompt}"
        try:
            async with async_playwright() as playwright:
                kwargs: dict = {"headless": self.headless}
                if self.executable:
                    kwargs["executable_path"] = str(self.executable)
                else:
                    kwargs["channel"] = "chrome"
                context = await playwright.chromium.launch_persistent_context(str(profile_dir), **kwargs)
                try:
                    page = context.pages[0] if context.pages else await context.new_page()
                    page.set_default_timeout(20_000)
                    await page.goto(target_url, wait_until="domcontentloaded", timeout=45_000)
                    await self._ensure_authenticated(page)
                    before_count = await page.locator('[data-message-author-role="assistant"]').count()
                    prompt_box = page.locator('#prompt-textarea, [contenteditable="true"][role="textbox"]').first
                    await prompt_box.wait_for(state="visible")
                    await prompt_box.fill(composed_prompt)
                    send_button = page.locator('[data-testid="send-button"], button[aria-label*="Send"]').first
                    await send_button.click()
                    answer = await self._wait_for_answer(page, before_count, request.timeout_seconds)
                    return ProviderResult(answer=answer, conversation_url=page.url)
                finally:
                    await context.close()
        except ProviderError:
            raise
        except PlaywrightError as exc:
            raise ProviderError("PAGE_LOAD_FAILED", str(exc)[:2000], retryable=True) from exc

    async def _ensure_authenticated(self, page) -> None:
        prompt = page.locator('#prompt-textarea, [contenteditable="true"][role="textbox"]').first
        try:
            await prompt.wait_for(state="visible", timeout=12_000)
            return
        except PlaywrightError:
            pass
        login_markers = page.locator('input[type="email"], input[name="email"], a[href*="login"], button:has-text("Log in"), button:has-text("登录")')
        if await login_markers.count() or "auth.openai.com" in page.url:
            raise ProviderError("AUTH_REQUIRED", "ChatGPT login is required. Run the browser login command for this profile.")
        raise ProviderError("CHAT_INPUT_NOT_FOUND", "ChatGPT input box was not found.", retryable=True)

    async def _wait_for_answer(self, page, before_count: int, timeout_seconds: int) -> str:
        answers = page.locator('[data-message-author-role="assistant"]')
        try:
            await page.wait_for_function(
                "([selector, count]) => document.querySelectorAll(selector).length > count",
                arg=['[data-message-author-role="assistant"]', before_count], timeout=timeout_seconds * 1000,
            )
            latest = answers.last
            previous = ""
            stable_count = 0
            for _ in range(max(3, timeout_seconds // 2)):
                current = (await latest.inner_text()).strip()
                stop = page.locator('[data-testid="stop-button"], button[aria-label*="Stop"], button[aria-label*="停止"]').first
                is_stopping = await stop.is_visible() if await stop.count() else False
                if current and current == previous and not is_stopping:
                    stable_count += 1
                    if stable_count >= 2:
                        return current
                else:
                    stable_count = 0
                previous = current
                await page.wait_for_timeout(1000)
        except PlaywrightError as exc:
            raise ProviderError("GENERATION_TIMEOUT", "Timed out waiting for a ChatGPT answer.", retryable=True) from exc
        raise ProviderError("GENERATION_TIMEOUT", "Timed out waiting for a stable ChatGPT answer.", retryable=True)


def build_provider(name: str, command: str | None, *, base_url: str, profiles_dir: Path,
                   headless: bool, executable: Path | None) -> ChatProvider:
    if name == "demo":
        return DemoProvider()
    if name == "openbrowser":
        return OpenBrowserProvider(base_url, profiles_dir, headless, executable)
    if name == "command":
        return CommandProvider(command)
    raise ValueError(f"Unsupported provider: {name}")
