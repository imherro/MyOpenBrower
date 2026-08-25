from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os

from dotenv import load_dotenv


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    host: str = "0.0.0.0"
    port: int = 9901
    db_path: Path = Path("data/chatgpt_gateway.db")
    worker_enabled: bool = True
    poll_interval_seconds: float = 0.5
    task_timeout_seconds: int = 300
    stale_task_seconds: int = 360
    provider: str = "openbrowser"
    openbrowser_command: str | None = None
    chatgpt_base_url: str = "https://chatgpt.com/"
    browser_profiles_dir: Path = Path("profiles")
    browser_headless: bool = False
    browser_executable: Path | None = None
    api_key: str | None = None
    log_dir: Path = Path("logs")
    failure_dir: Path = Path("data/failures")

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv(override=False)
        return cls(
            host=os.getenv("GATEWAY_HOST", "0.0.0.0"),
            port=int(os.getenv("GATEWAY_PORT", "9901")),
            db_path=Path(os.getenv("GATEWAY_DB_PATH", "data/chatgpt_gateway.db")),
            worker_enabled=_as_bool(os.getenv("GATEWAY_WORKER_ENABLED"), True),
            poll_interval_seconds=float(os.getenv("GATEWAY_POLL_INTERVAL_SECONDS", "0.5")),
            task_timeout_seconds=int(os.getenv("GATEWAY_TASK_TIMEOUT_SECONDS", "300")),
            stale_task_seconds=int(os.getenv("GATEWAY_STALE_TASK_SECONDS", "360")),
            provider=os.getenv("GATEWAY_PROVIDER", "openbrowser").lower(),
            openbrowser_command=os.getenv("GATEWAY_OPENBROWSER_COMMAND") or None,
            chatgpt_base_url=os.getenv("GATEWAY_CHATGPT_BASE_URL", "https://chatgpt.com/"),
            browser_profiles_dir=Path(os.getenv("GATEWAY_BROWSER_PROFILES_DIR", "profiles")),
            browser_headless=_as_bool(os.getenv("GATEWAY_BROWSER_HEADLESS"), False),
            browser_executable=Path(os.environ["GATEWAY_BROWSER_EXECUTABLE"]) if os.getenv("GATEWAY_BROWSER_EXECUTABLE") else None,
            api_key=os.getenv("GATEWAY_API_KEY") or None,
            log_dir=Path(os.getenv("GATEWAY_LOG_DIR", "logs")),
            failure_dir=Path(os.getenv("GATEWAY_FAILURE_DIR", "data/failures")),
        )
