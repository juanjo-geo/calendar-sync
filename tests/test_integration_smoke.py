import pytest
from unittest.mock import patch, MagicMock
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.sync import run_sync

CONFIG_TEST = {
    "timezone": "America/Bogota",
    "sync_window_days_past": 7,
    "sync_window_days_future": 60,
    "schedule": {
        "allowed_days": ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"],
        "allowed_hours_start": "00:00",
        "allowed_hours_end": "23:59"
    },
    "behavior": {
        "delete_cancelled_events": True,
        "sync_private_events": False,
        "add_sync_tag_to_description": True,
        "sync_tag": "[Sync: Outlook]"
    },
    "microsoft": {
        "tenant_id": "test_tenant",
        "client_id": "test_client",
        "scopes": ["Calendars.Read"]
    },
    "google": {
        "calendar_id": "primary"
    }
}

RAW_EVENTO_NUEVO = {
    "id": "outlook_nuevo_001",
    "subject": "Evento Nuevo",
    "start": {"dateTime": "2026-03-25T10:00:00", "timeZone": "America/Bogota"},
    "end": {"dateTime": "2026-03-25T11:00:00", "timeZone": "America/Bogota"},
    "location": {"displayName": "Sala B"},
    "body": {"content": "Descripcion"},
    "isCancelled": False,
    "isAllDay": False,
    "type": "singleInstance",
    "showAs": "busy",
    "seriesMasterId": None,
    "originalStart": None
}

RAW_EVENTO_EXISTENTE = {
    "id": "outlook_existente_002",
    "subject": "Evento Sin Cambios",
    "start": {"dateTime": "2026-03-25T14:00:00", "timeZone": "America/Bogota"},
    "end": {"dateTime": "2026-03-25T15:00:00", "timeZone": "America/Bogota"},
    "location": None,
    "body": {"content": ""},
    "isCancelled": False,
    "isAllDay": False,
    "type": "singleInstance",
    "showAs": "busy",
    "seriesMasterId": None,
    "originalStart": None
}

def test_smoke_sync_completo():
    from app.transformers import compute_fingerprint, outlook_to_internal

    internal_existente = outlook_to_internal(RAW_EVENTO_EXISTENTE, CONFIG_TEST)
    fingerprint_existente = compute_fingerprint(internal_existente)

    estado_inicial = {
        "last_run": None,
        "events_map": {"outlook_existente_002": "google_existente_002"},
        "event_fingerprints": {"outlook_existente_002": fingerprint_existente}
    }

    mock_create = MagicMock(return_value="google_nuevo_001")
    mock_update = MagicMock()
    mock_delete = MagicMock()

    with patch("app.sync.load_config", return_value=CONFIG_TEST), \
         patch("app.sync.load_state", return_value=estado_inicial), \
         patch("app.sync.save_state"), \
         patch("app.sync.is_sync_allowed", return_value=True), \
         patch("app.sync.OutlookClient") as MockOutlook, \
         patch("app.sync.GoogleCalendarClient") as MockGoogle:

        MockOutlook.return_value.get_calendar_events.return_value = [
            RAW_EVENTO_NUEVO,
            RAW_EVENTO_EXISTENTE
        ]
        MockGoogle.return_value.create_event = mock_create
        MockGoogle.return_value.update_event = mock_update
        MockGoogle.return_value.delete_event = mock_delete

        run_sync()

    mock_create.assert_called_once()
    mock_update.assert_not_called()
    mock_delete.assert_not_called()
