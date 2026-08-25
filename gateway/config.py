from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    host: str = "0.0.0.0"
    port: int = 9900
    db_path: Path = Path("data/chatgpt_gateway.db")
    worker_enabled: bool = True
    poll_interval_seconds: float = 0.5
    task_timeout_seconds: int = 300
    stale_task_seconds: int = 360
    provider: str = "openbrowser"
    openbrowser_command: str | None = None

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            host=os.getenv("GATEWAY_HOST", "0.0.0.0"),
            port=int(os.getenv("GATEWAY_PORT", "9900")),
            db_path=Path(os.getenv("GATEWAY_DB_PATH", "data/chatgpt_gateway.db")),
            worker_enabled=_as_bool(os.getenv("GATEWAY_WORKER_ENABLED"), True),
            poll_interval_seconds=float(os.getenv("GATEWAY_POLL_INTERVAL_SECONDS", "0.5")),
            task_timeout_seconds=int(os.getenv("GATEWAY_TASK_TIMEOUT_SECONDS", "300")),
            stale_task_seconds=int(os.getenv("GATEWAY_STALE_TASK_SECONDS", "360")),
            provider=os.getenv("GATEWAY_PROVIDER", "openbrowser").lower(),
            openbrowser_command=os.getenv("GATEWAY_OPENBROWSER_COMMAND") or None,
        )
