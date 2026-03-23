import os

import msal
import requests

from app.logger import get_logger


class OutlookClient:

    def __init__(self, config: dict) -> None:
        ms = config["microsoft"]
        tenant_id = ms["tenant_id"]
        client_id = ms["client_id"]

        client_secret = os.environ.get("MICROSOFT_CLIENT_SECRET")
        if not client_secret:
            raise EnvironmentError(
                "MICROSOFT_CLIENT_SECRET environment variable is not set. "
                "Add it to your .env file or CI secrets."
            )

        self._scopes = ms["scopes"]
        self._app = msal.ConfidentialClientApplication(
            client_id=client_id,
            client_credential=client_secret,
            authority=f"https://login.microsoftonline.com/{tenant_id}",
        )
        self._logger = get_logger()

    def _get_token(self) -> str:
        result = self._app.acquire_token_silent(self._scopes, account=None)
        if not result:
            result = self._app.acquire_token_for_client(scopes=self._scopes)
        if "error" in result:
            raise RuntimeError(
                f"MSAL token error: {result['error']} — {result.get('error_description', '')}"
            )
        return result["access_token"]

    def get_calendar_events(self, start_dt, end_dt) -> list:
        token = self._get_token()
        headers = {"Authorization": f"Bearer {token}"}
        params = {
            "startDateTime": start_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "endDateTime": end_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "$top": 100,
        }

        url = "https://graph.microsoft.com/v1.0/me/calendarView"
        events = []

        while url:
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()
            events.extend(data.get("value", []))
            url = data.get("@odata.nextLink")
            params = None  # nextLink already contains query params

        self._logger.debug("Fetched %d events from Outlook", len(events))
        return events
