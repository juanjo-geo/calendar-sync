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
