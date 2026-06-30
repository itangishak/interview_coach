"""Logging setup."""

from pathlib import Path

from loguru import logger


def setup_logging(log_dir: str = "./logs") -> None:
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    logger.add(
        Path(log_dir) / "inference.log",
        rotation="1 MB",
        retention="7 days",
        level="INFO",
    )