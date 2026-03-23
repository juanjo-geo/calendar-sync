import logging
import os
import sys
from pathlib import Path

_LOG_FORMAT = "[%(asctime)s] %(levelname)s - %(message)s"
_LOGGER_NAME = "calendar_sync"


def get_logger() -> logging.Logger:
    logger = logging.getLogger(_LOGGER_NAME)

    if logger.handlers:
        return logger

    raw_level = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, raw_level, logging.INFO)
    logger.setLevel(level)

    formatter = logging.Formatter(_LOG_FORMAT)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    file_handler = logging.FileHandler(log_dir / "sync.log", encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger
