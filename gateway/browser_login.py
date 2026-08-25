"""Open an isolated persistent Chrome profile so the user can sign in to ChatGPT once."""

from __future__ import annotations

import argparse
import asyncio

from playwright.async_api import async_playwright

from gateway.config import Settings


async def login(profile_name: str) -> None:
    settings = Settings.from_env()
    profile_dir = settings.browser_profiles_dir / profile_name
    profile_dir.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as playwright:
        kwargs: dict = {"headless": False}
        if settings.browser_executable:
            kwargs["executable_path"] = str(settings.browser_executable)
        else:
            kwargs["channel"] = "chrome"
        context = await playwright.chromium.launch_persistent_context(str(profile_dir), **kwargs)
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(settings.chatgpt_base_url, wait_until="domcontentloaded")
        input("Complete ChatGPT login in the opened Chrome window, then press Enter here to save the profile... ")
        await context.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Log in to ChatGPT for a gateway browser profile.")
    parser.add_argument("--profile", default="default", help="Profile name configured for the gateway session.")
    arguments = parser.parse_args()
    asyncio.run(login(arguments.profile))
