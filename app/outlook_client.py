import os
from datetime import date, datetime

import pytz
import requests
from icalendar import Calendar

from app.logger import get_logger


class OutlookClient:

    def __init__(self, config: dict) -> None:
        self._logger = get_logger()
        self._config = config

        ics_url = os.environ.get("OUTLOOK_ICS_URL")
        if not ics_url:
            raise EnvironmentError(
                "OUTLOOK_ICS_URL environment variable is not set. "
                "Export the ICS URL from Outlook and add it to your .env file or CI secrets."
            )
        self.ics_url = ics_url

    def get_calendar_events(self, start_dt: datetime, end_dt: datetime) -> list:
        try:
            response = requests.get(self.ics_url, timeout=30)
            response.raise_for_status()
        except requests.RequestException as exc:
            self._logger.error("Failed to fetch ICS feed: %s", exc)
            return []

        try:
            cal = Calendar.from_ical(response.content)
        except Exception as exc:
            self._logger.error("Failed to parse ICS content: %s", exc)
            return []

        events = []
        for component in cal.walk():
            if component.name != "VEVENT":
                continue

            raw = self._vevent_to_dict(component)
            if raw is None:
                continue

            # Filter by sync window
            event_start = self._parse_dtstart_utc(component)
            if event_start is None:
                continue
            if not (start_dt <= event_start <= end_dt):
                continue

            events.append(raw)

        self._logger.debug("Fetched %d events from ICS feed within sync window", len(events))
        return events

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _vevent_to_dict(self, event) -> dict | None:
        try:
            dtstart_raw = event.decoded("DTSTART")
            dtend_raw = event.decoded("DTEND", None) or event.decoded("DURATION", None)
        except Exception:
            return None

        is_all_day = isinstance(dtstart_raw, date) and not isinstance(dtstart_raw, datetime)

        if is_all_day:
            start_str = dtstart_raw.strftime("%Y-%m-%dT00:00:00")
            if isinstance(dtend_raw, date) and not isinstance(dtend_raw, datetime):
                end_str = dtend_raw.strftime("%Y-%m-%dT00:00:00")
            else:
                end_str = start_str
            tz_name = self._config.get("timezone", "UTC")
        else:
            tz_name = self._extract_tzname(dtstart_raw)
            start_str = self._dt_to_str(dtstart_raw)
            end_str = self._dt_to_str(dtend_raw) if isinstance(dtend_raw, datetime) else start_str

        location_val = event.get("LOCATION")
        location = {"displayName": str(location_val)} if location_val else None

        return {
            "id": str(event.get("UID", "")),
            "subject": str(event.get("SUMMARY", "")),
            "start": {"dateTime": start_str, "timeZone": tz_name},
            "end": {"dateTime": end_str, "timeZone": tz_name},
            "location": location,
            "body": {"content": str(event.get("DESCRIPTION", ""))},
            "isCancelled": str(event.get("STATUS", "")).upper() == "CANCELLED",
            "isAllDay": is_all_day,
            "type": "singleInstance",
            "showAs": "busy",
            "seriesMasterId": None,
            "originalStart": None,
        }

    def _parse_dtstart_utc(self, event) -> datetime | None:
        """Returns DTSTART as a timezone-aware UTC datetime for range filtering."""
        try:
            dtstart = event.decoded("DTSTART")
        except Exception:
            return None

        if isinstance(dtstart, datetime):
            if dtstart.tzinfo is None:
                tz_name = self._config.get("timezone", "UTC")
                local_tz = pytz.timezone(tz_name)
                dtstart = local_tz.localize(dtstart)
            return dtstart.astimezone(pytz.utc)

        if isinstance(dtstart, date):
            tz_name = self._config.get("timezone", "UTC")
            local_tz = pytz.timezone(tz_name)
            naive = datetime(dtstart.year, dtstart.month, dtstart.day, 0, 0, 0)
            return local_tz.localize(naive).astimezone(pytz.utc)

        return None

    @staticmethod
    def _extract_tzname(dt: datetime) -> str:
        if dt.tzinfo is not None:
            name = dt.tzinfo.tzname(dt)
            if name:
                return name
        return "UTC"

    @staticmethod
    def _dt_to_str(dt: datetime) -> str:
        return dt.strftime("%Y-%m-%dT%H:%M:%S")
