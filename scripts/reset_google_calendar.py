"""
Borra del Google Calendar todos los eventos creados por el sync
(identificados por la etiqueta [Sync: Outlook] en la descripción).
Maneja paginación y resetea data/state.json al finalizar.

Uso:
    $env:GOOGLE_CREDENTIALS_JSON = (Get-Content "credentials.json" -Raw)
    python scripts/reset_google_calendar.py
"""

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from google.oauth2 import credentials as oauth2_credentials
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

STATE_PATH = Path(__file__).parent.parent / "data" / "state.json"
CONFIG_PATH = Path(__file__).parent.parent / "data" / "config.json"
_SCOPES = ["https://www.googleapis.com/auth/calendar"]
_SYNC_TAG = "[Sync: Outlook]"


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


def list_all_events(service, calendar_id: str) -> list:
    """Fetches all events with full pagination."""
    all_events = []
    page_token = None

    while True:
        kwargs = {
            "calendarId": calendar_id,
            "maxResults": 250,
            "singleEvents": True,
        }
        if page_token:
            kwargs["pageToken"] = page_token

        response = service.events().list(**kwargs).execute()
        all_events.extend(response.get("items", []))
        page_token = response.get("nextPageToken")

        print(f"  Fetched {len(all_events)} eventos...", end="\r")

        if not page_token:
            break

    print()
    return all_events


def main():
    with CONFIG_PATH.open(encoding="utf-8") as f:
        config = json.load(f)
    calendar_id = config["google"]["calendar_id"]

    print(f"\nCalendario : {calendar_id}")
    print(f"Buscando eventos con '{_SYNC_TAG}' en la descripción...\n")

    service = build_service()

    all_events = list_all_events(service, calendar_id)
    print(f"Total eventos en el calendario : {len(all_events)}")

    sync_events = [
        e for e in all_events
        if _SYNC_TAG in (e.get("description") or "")
    ]
    print(f"Eventos con '{_SYNC_TAG}'       : {len(sync_events)}\n")

    if not sync_events:
        print("Nada que borrar.")
    else:
        deleted = 0
        errors = 0
        for i, event in enumerate(sync_events):
            event_id = event["id"]
            title = event.get("summary", "(sin titulo)")
            try:
                service.events().delete(
                    calendarId=calendar_id, eventId=event_id
                ).execute()
                print(f"  Deleted: {title}")
                deleted += 1
            except HttpError as exc:
                if exc.resp.status in (404, 410):
                    print(f"  Skipped (ya borrado): {title}")
                elif exc.resp.status == 403:
                    # Rate limit — wait and retry once
                    time.sleep(2)
                    try:
                        service.events().delete(
                            calendarId=calendar_id, eventId=event_id
                        ).execute()
                        print(f"  Deleted (retry): {title}")
                        deleted += 1
                    except HttpError:
                        print(f"  ERROR (rate limit): {title}")
                        errors += 1
                else:
                    print(f"  ERROR borrando '{title}': {exc}")
                    errors += 1
            # Throttle: small pause every 10 deletes to avoid rate limits
            if (i + 1) % 10 == 0:
                time.sleep(0.5)

        print(f"\nTotal deleted : {deleted} eventos")
        if errors:
            print(f"Errores       : {errors}")

    # Reset state.json
    clean_state = {"last_run": None, "events_map": {}, "event_fingerprints": {}}
    with STATE_PATH.open("w", encoding="utf-8") as f:
        json.dump(clean_state, f, indent=2)
    print("state.json    : reseteado OK\n")


if __name__ == "__main__":
    main()
