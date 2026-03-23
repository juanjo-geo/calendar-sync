import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import load_config

def test_load_config_retorna_dict():
    config = load_config()
    assert isinstance(config, dict)
    assert "timezone" in config
    assert config["timezone"] == "America/Bogota"

def test_load_config_tiene_campos_microsoft():
    config = load_config()
    assert "microsoft" in config
    assert "tenant_id" in config["microsoft"]
    assert "client_id" in config["microsoft"]

def test_load_config_tiene_google():
    config = load_config()
    assert "google" in config
    assert "calendar_id" in config["google"]


from app.state_store import (
    load_state, save_state, get_google_event_id,
    set_event_mapping, remove_event_mapping,
    get_fingerprint, set_fingerprint
)

def test_state_inicial_limpio():
    state = load_state()
    assert "events_map" in state
    assert "event_fingerprints" in state
    assert "last_run" in state

def test_set_y_get_event_mapping():
    state = load_state()
    state = set_event_mapping("outlook_123", "google_456", state)
    result = get_google_event_id("outlook_123", state)
    assert result == "google_456"

def test_remove_event_mapping():
    state = load_state()
    state = set_event_mapping("outlook_999", "google_999", state)
    state = remove_event_mapping("outlook_999", state)
    assert get_google_event_id("outlook_999", state) is None

def test_set_y_get_fingerprint():
    state = load_state()
    state = set_fingerprint("key_abc", "fingerprint_xyz", state)
    assert get_fingerprint("key_abc", state) == "fingerprint_xyz"

def test_get_fingerprint_inexistente():
    state = load_state()
    assert get_fingerprint("no_existe", state) is None


# ---------------------------------------------------------------------------
# Transformer tests
# ---------------------------------------------------------------------------

from app.transformers import outlook_to_internal, internal_to_google, compute_fingerprint

CONFIG = {
    "timezone": "America/Bogota",
    "behavior": {
        "sync_private_events": False,
        "add_sync_tag_to_description": True,
        "sync_tag": "[Sync: Outlook]"
    }
}

RAW_EVENTO_UNICO = {
    "id": "outlook_abc123",
    "subject": "Reunión de equipo",
    "start": {"dateTime": "2026-03-23T15:00:00", "timeZone": "America/Bogota"},
    "end": {"dateTime": "2026-03-23T16:00:00", "timeZone": "America/Bogota"},
    "location": {"displayName": "Sala A"},
    "body": {"content": "<p>Descripción del evento</p>"},
    "isCancelled": False,
    "isAllDay": False,
    "type": "singleInstance",
    "showAs": "busy",
    "seriesMasterId": None,
    "originalStart": None,
}

RAW_EVENTO_RECURRENTE = {
    "id": "outlook_occ456",
    "subject": "Standup diario",
    "start": {"dateTime": "2026-03-23T09:00:00", "timeZone": "America/Bogota"},
    "end": {"dateTime": "2026-03-23T09:30:00", "timeZone": "America/Bogota"},
    "location": None,
    "body": {"content": ""},
    "isCancelled": False,
    "isAllDay": False,
    "type": "occurrence",
    "showAs": "busy",
    "seriesMasterId": "master_789",
    "originalStart": "2026-03-23T09:00:00",
}

RAW_EVENTO_PRIVADO = {
    **RAW_EVENTO_UNICO,
    "id": "outlook_priv999",
    "sensitivity": "private",
}


# --- outlook_to_internal ---

def test_outlook_to_internal_campos_basicos():
    internal = outlook_to_internal(RAW_EVENTO_UNICO, CONFIG)
    assert internal is not None
    assert internal["outlook_id"] == "outlook_abc123"
    assert internal["title"] == "Reunión de equipo"
    assert internal["is_all_day"] is False
    assert internal["is_cancelled"] is False
    assert internal["location"] == "Sala A"
    assert internal["event_type"] == "singleInstance"

def test_outlook_to_internal_convierte_a_utc():
    internal = outlook_to_internal(RAW_EVENTO_UNICO, CONFIG)
    # Bogotá = UTC-5, 15:00 → 20:00Z
    assert internal["start"] == "2026-03-23T20:00:00Z"
    assert internal["end"] == "2026-03-23T21:00:00Z"

def test_outlook_to_internal_event_key_unico():
    internal = outlook_to_internal(RAW_EVENTO_UNICO, CONFIG)
    assert internal["event_key"] == "outlook_abc123"

def test_outlook_to_internal_event_key_recurrente():
    internal = outlook_to_internal(RAW_EVENTO_RECURRENTE, CONFIG)
    assert internal is not None
    assert internal["event_key"].startswith("master_789|")
    assert internal["series_master_id"] == "master_789"

def test_outlook_to_internal_skips_privado():
    result = outlook_to_internal(RAW_EVENTO_PRIVADO, CONFIG)
    assert result is None


# --- internal_to_google ---

def test_internal_to_google_estructura():
    internal = outlook_to_internal(RAW_EVENTO_UNICO, CONFIG)
    google_body = internal_to_google(internal, CONFIG)
    assert "summary" in google_body
    assert "start" in google_body
    assert "end" in google_body
    assert google_body["summary"] == "Reunión de equipo"
    assert google_body["start"]["timeZone"] == "UTC"

def test_internal_to_google_agrega_sync_tag():
    internal = outlook_to_internal(RAW_EVENTO_UNICO, CONFIG)
    google_body = internal_to_google(internal, CONFIG)
    assert "[Sync: Outlook]" in (google_body.get("description") or "")

def test_internal_to_google_sync_tag_no_duplicado():
    internal = outlook_to_internal(RAW_EVENTO_UNICO, CONFIG)
    google_body = internal_to_google(internal, CONFIG)
    desc = google_body.get("description", "")
    assert desc.count("[Sync: Outlook]") == 1


# --- compute_fingerprint ---

def test_compute_fingerprint_es_string_hex():
    internal = outlook_to_internal(RAW_EVENTO_UNICO, CONFIG)
    fp = compute_fingerprint(internal)
    assert isinstance(fp, str)
    assert len(fp) == 64  # SHA-256 hex digest

def test_compute_fingerprint_estable():
    internal = outlook_to_internal(RAW_EVENTO_UNICO, CONFIG)
    assert compute_fingerprint(internal) == compute_fingerprint(internal)

def test_compute_fingerprint_cambia_con_titulo():
    internal = outlook_to_internal(RAW_EVENTO_UNICO, CONFIG)
    modified = {**internal, "title": "Otro título"}
    assert compute_fingerprint(internal) != compute_fingerprint(modified)
