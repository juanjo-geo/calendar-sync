"""
Borra del Google Calendar todos los eventos creados por el sync,
usando los IDs registrados en data/state.json.

Uso:
    $env:GOOGLE_CREDENTIALS_JSON = (Get-Content "C:/Users/.../calendar-sync-*.json" -Raw)
    python scripts/reset_google_calendar.py
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from google.oauth2 import service_account
from google.oauth2 import credentials as oauth2_credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

STATE_PATH = Path(__file__).parent.parent / "data" / "state.json"
CONFIG_PATH = Path(__file__).parent.parent / "data" / "config.json"
_SCOPES = ["https://www.googleapis.com/auth/calendar"]


def build_service():
    raw = os.environ.get("GOOGLE_CREDENTIALS_JSON")
    if not raw:
        print("ERROR: GOOGLE_CREDENTIALS_JSON no está definida.")
        sys.exit(1)

    creds_dict = json.loads(raw)

    if creds_dict.get("type") == "service_account":
        creds = service_account.Credentials.from_service_account_info(
            creds_dict, scopes=_SCOPES
        )
    elif "refresh_token" in creds_dict:
        creds = oauth2_credentials.Credentials(
            token=creds_dict.get("token"),
            refresh_token=creds_dict["refresh_token"],
            token_uri=creds_dict.get("token_uri", "https://oauth2.googleapis.com/token"),
            client_id=creds_dict.get("client_id"),
            client_secret=creds_dict.get("client_secret"),
        )
    else:
        print("ERROR: Formato de credenciales no reconocido.")
        sys.exit(1)

    return build("calendar", "v3", credentials=creds)


def main():
    # Load config
    with CONFIG_PATH.open(encoding="utf-8") as f:
        config = json.load(f)
    calendar_id = config["google"]["calendar_id"]

    # Load state
    if not STATE_PATH.exists():
        print("data/state.json no existe — nada que borrar.")
        return

    with STATE_PATH.open(encoding="utf-8") as f:
        state = json.load(f)

    events_map: dict = state.get("events_map", {})
    if not events_map:
        print("events_map vacío — nada que borrar.")
        return

    print(f"\nCalendario : {calendar_id}")
    print(f"Eventos a borrar : {len(events_map)}\n")

    service = build_service()
    deleted = 0
    errors = 0

    for outlook_id, google_id in events_map.items():
        try:
            # Fetch title for display before deleting
            try:
                event = service.events().get(
                    calendarId=calendar_id, eventId=google_id
                ).execute()
                title = event.get("summary", "(sin título)")
            except HttpError:
                title = f"(no encontrado: {google_id})"

            service.events().delete(
                calendarId=calendar_id, eventId=google_id
            ).execute()
            print(f"  Deleted: {title}")
            deleted += 1

        except HttpError as exc:
            if exc.resp.status in (404, 410):
                print(f"  Skipped (ya borrado): {google_id}")
            else:
                print(f"  ERROR borrando {google_id}: {exc}")
                errors += 1

    # Reset state.json
    clean_state = {"last_run": None, "events_map": {}, "event_fingerprints": {}}
    with STATE_PATH.open("w", encoding="utf-8") as f:
        json.dump(clean_state, f, indent=2)

    print(f"\nTotal deleted : {deleted} eventos")
    if errors:
        print(f"Errores       : {errors}")
    print("state.json    : reseteado ✓\n")


if __name__ == "__main__":
    main()
