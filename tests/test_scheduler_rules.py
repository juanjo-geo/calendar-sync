import pytest
from unittest.mock import patch
from datetime import datetime
import pytz
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.scheduler_rules import is_sync_allowed, get_sync_window

CONFIG = {
    "timezone": "America/Bogota",
    "sync_window_days_past": 7,
    "sync_window_days_future": 60,
    "schedule": {
        "allowed_days": ["Monday","Tuesday","Wednesday","Thursday","Friday"],
        "allowed_hours_start": "06:00",
        "allowed_hours_end": "23:00"
    }
}

def test_sync_allowed_dia_y_hora_validos():
    # Simular lunes a las 10:00 AM en Bogotá
    bogota = pytz.timezone("America/Bogota")
    fake_now = bogota.localize(datetime(2026, 3, 23, 10, 0, 0))  # lunes
    with patch("app.scheduler_rules.datetime") as mock_dt:
        mock_dt.now.return_value = fake_now
        assert is_sync_allowed(CONFIG) == True

def test_sync_not_allowed_hora_fuera_de_rango():
    # Simular lunes a las 02:00 AM (fuera de rango)
    bogota = pytz.timezone("America/Bogota")
    fake_now = bogota.localize(datetime(2026, 3, 23, 2, 0, 0))
    with patch("app.scheduler_rules.datetime") as mock_dt:
        mock_dt.now.return_value = fake_now
        assert is_sync_allowed(CONFIG) == False

def test_sync_not_allowed_fin_de_semana():
    # Simular sábado a las 10:00 AM
    bogota = pytz.timezone("America/Bogota")
    fake_now = bogota.localize(datetime(2026, 3, 21, 10, 0, 0))  # sábado
    with patch("app.scheduler_rules.datetime") as mock_dt:
        mock_dt.now.return_value = fake_now
        assert is_sync_allowed(CONFIG) == False

def test_get_sync_window_retorna_tuple():
    start, end = get_sync_window(CONFIG)
    assert start < end
    assert start.tzinfo is not None  # timezone-aware
    assert end.tzinfo is not None

def test_get_sync_window_rango_correcto():
    from datetime import timedelta
    start, end = get_sync_window(CONFIG)
    now = datetime.now(tz=pytz.utc)
    assert abs((now - start).days - 7) <= 1
    assert abs((end - now).days - 60) <= 1
