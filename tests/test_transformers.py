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
