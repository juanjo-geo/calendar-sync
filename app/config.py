import json
import os
from pathlib import Path

from app.logger import get_logger

_CONFIG_PATH = Path(__file__).parent.parent / "data" / "config.json"

_REQUIRED_FIELDS = [
    ("timezone",),
    ("microsoft", "tenant_id"),
    ("microsoft", "client_id"),
    ("google", "calendar_id"),
]


def _get_nested(data: dict, keys: tuple) -> object:
    """Traverses nested dicts following the given key path. Returns None if any key is missing."""
    node = data
    for key in keys:
        if not isinstance(node, dict) or key not in node:
            return None
        node = node[key]
    return node


def _validate(data: dict) -> None:
    missing = [
        ".".join(path)
        for path in _REQUIRED_FIELDS
        if not _get_nested(data, path)
    ]
    if missing:
        raise ValueError(
            f"config.json is missing required field(s): {', '.join(missing)}"
        )


def load_config() -> dict:
    logger = get_logger()

    if not _CONFIG_PATH.exists():
        raise FileNotFoundError(f"Configuration file not found: {_CONFIG_PATH}")

    with _CONFIG_PATH.open(encoding="utf-8") as f:
        config = json.load(f)

    _validate(config)

    # Attach runtime secrets from environment — never stored in config.json
    config["microsoft"]["client_secret"] = os.environ.get("MICROSOFT_CLIENT_SECRET")
    config["google"]["credentials_json"] = os.environ.get("GOOGLE_CREDENTIALS_JSON")

    logger.info("Configuration loaded from %s", _CONFIG_PATH)
    return config
