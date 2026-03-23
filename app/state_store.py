import json
from pathlib import Path

from app.logger import get_logger

_STATE_PATH = Path(__file__).parent.parent / "data" / "state.json"

_INITIAL_STATE: dict = {
    "last_run": None,
    "events_map": {},
    "event_fingerprints": {},
}


def load_state() -> dict:
    logger = get_logger()
    try:
        with _STATE_PATH.open(encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        logger.warning("state.json not found — starting with clean state")
    except json.JSONDecodeError as exc:
        logger.error("state.json is corrupted (%s) — starting with clean state", exc)
    return _fresh_state()


def save_state(state: dict) -> None:
    logger = get_logger()
    tmp_path = _STATE_PATH.with_suffix(".json.tmp")
    try:
        with tmp_path.open("w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
        tmp_path.replace(_STATE_PATH)
    except OSError as exc:
        logger.error("Failed to save state: %s", exc)
        raise


def get_google_event_id(outlook_event_id: str, state: dict) -> str | None:
    return state.get("events_map", {}).get(outlook_event_id)


def set_event_mapping(outlook_id: str, google_id: str, state: dict) -> dict:
    state.setdefault("events_map", {})[outlook_id] = google_id
    return state


def remove_event_mapping(outlook_id: str, state: dict) -> dict:
    state.setdefault("events_map", {}).pop(outlook_id, None)
    return state


def get_fingerprint(event_key: str, state: dict) -> str | None:
    return state.get("event_fingerprints", {}).get(event_key)


def set_fingerprint(event_key: str, fingerprint: str, state: dict) -> dict:
    state.setdefault("event_fingerprints", {})[event_key] = fingerprint
    return state


def _fresh_state() -> dict:
    return {k: (v.copy() if isinstance(v, dict) else v) for k, v in _INITIAL_STATE.items()}
