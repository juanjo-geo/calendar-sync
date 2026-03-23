import json
import os

from google.oauth2 import credentials as oauth2_credentials
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.logger import get_logger

_CALENDAR_SCOPES = ["https://www.googleapis.com/auth/calendar"]


class GoogleCalendarClient:

    def __init__(self, config: dict) -> None:
        self._logger = get_logger()

        raw = os.environ.get("GOOGLE_CREDENTIALS_JSON")
        if not raw:
            raise EnvironmentError(
                "GOOGLE_CREDENTIALS_JSON environment variable is not set. "
                "Add the credentials JSON string to your .env file or CI secrets."
            )

        creds_dict = json.loads(raw)

        if creds_dict.get("type") == "service_account":
            creds = service_account.Credentials.from_service_account_info(
                creds_dict, scopes=_CALENDAR_SCOPES
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
            raise ValueError(
                "GOOGLE_CREDENTIALS_JSON must be a service account JSON or contain a refresh_token. "
                f"Found type: {creds_dict.get('type', 'unknown')!r}"
            )

        self._service = build("calendar", "v3", credentials=creds)
        self.calendar_id = config["google"]["calendar_id"]

    def create_event(self, event_body: dict) -> str:
        result = (
            self._service.events()
            .insert(calendarId=self.calendar_id, body=event_body)
            .execute()
        )
        event_id = result["id"]
        self._logger.info("Created Google event: %s", event_id)
        return event_id

    def update_event(self, google_event_id: str, event_body: dict) -> None:
        self._service.events().patch(
            calendarId=self.calendar_id,
            eventId=google_event_id,
            body=event_body,
        ).execute()
        self._logger.info("Updated Google event: %s", google_event_id)

    def delete_event(self, google_event_id: str) -> None:
        try:
            self._service.events().delete(
                calendarId=self.calendar_id,
                eventId=google_event_id,
            ).execute()
            self._logger.info("Deleted Google event: %s", google_event_id)
        except HttpError as exc:
            if exc.resp.status == 410:
                self._logger.warning(
                    "Google event %s already deleted (410 Gone)", google_event_id
                )
            else:
                raise

    def get_event(self, google_event_id: str) -> dict | None:
        try:
            return (
                self._service.events()
                .get(calendarId=self.calendar_id, eventId=google_event_id)
                .execute()
            )
        except HttpError as exc:
            if exc.resp.status == 404:
                self._logger.warning("Google event %s not found (404)", google_event_id)
                return None
            raise
