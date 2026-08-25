from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def configure_logging(log_dir: Path) -> None:
    """Configure a bounded, UTF-8 application log without duplicate handlers."""
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("gateway")
    logger.setLevel(logging.INFO)
    if any(isinstance(handler, RotatingFileHandler) for handler in logger.handlers):
        return
    handler = RotatingFileHandler(log_dir / "gateway.log", maxBytes=5_000_000, backupCount=5, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logger.addHandler(handler)
