import os
from datetime import date, datetime, timedelta

import pytz
import requests
from dateutil import rrule as dateutil_rrule
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
        seen_keys: set = set()
        for component in cal.walk():
            if component.name != "VEVENT":
                continue

            has_rrule = component.get("RRULE") is not None

            if has_rrule:
                # Expand RRULE occurrences within the sync window and emit one
                # dict per occurrence instead of the master event.
                expanded = self._expand_rrule(component, start_dt, end_dt)
                for raw in expanded:
                    event_key = raw["id"]
                    if event_key in seen_keys:
                        self._logger.debug("Skipping duplicate event_key: %s", event_key)
                        continue
                    seen_keys.add(event_key)
                    events.append(raw)
                continue

            raw = self._vevent_to_dict(component)
            if raw is None:
                continue

            event_start = self._parse_dtstart_utc(component)
            if event_start is None or not (start_dt <= event_start <= end_dt):
                continue

            # Deduplicate: skip if this event_key was already processed
            event_key = raw["id"]
            if event_key in seen_keys:
                self._logger.debug("Skipping duplicate event_key: %s", event_key)
                continue
            seen_keys.add(event_key)

            events.append(raw)

        self._logger.debug("Fetched %d events from ICS feed within sync window", len(events))
        return events

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _expand_rrule(self, component, start_dt: datetime, end_dt: datetime) -> list:
        """Expand a RRULE VEVENT into individual occurrence dicts within [start_dt, end_dt]."""
        try:
            dtstart_raw = component.decoded("DTSTART")
            dtend_raw = component.decoded("DTEND", None) or component.decoded("DURATION", None)
        except Exception:
            return []

        is_all_day = isinstance(dtstart_raw, date) and not isinstance(dtstart_raw, datetime)

        # Compute original duration
        if isinstance(dtstart_raw, datetime) and isinstance(dtend_raw, datetime):
            duration = dtend_raw - dtstart_raw
        elif isinstance(dtstart_raw, date) and isinstance(dtend_raw, date):
            duration = timedelta(days=(dtend_raw - dtstart_raw).days)
        else:
            duration = timedelta(hours=1)

        # Build a timezone-aware dtstart for dateutil
        if isinstance(dtstart_raw, datetime):
            if dtstart_raw.tzinfo is None:
                tz_name = self._config.get("timezone", "UTC")
                local_tz = pytz.timezone(tz_name)
                dtstart_aware = local_tz.localize(dtstart_raw)
            else:
                dtstart_aware = dtstart_raw
        else:
            # all-day date
            tz_name = self._config.get("timezone", "UTC")
            local_tz = pytz.timezone(tz_name)
            dtstart_aware = local_tz.localize(
                datetime(dtstart_raw.year, dtstart_raw.month, dtstart_raw.day)
            )

        # Parse the RRULE string via dateutil
        rrule_prop = component.get("RRULE")
        rrule_str = f"RRULE:{rrule_prop.to_ical().decode()}"
        try:
            ruleset = dateutil_rrule.rrulestr(
                rrule_str,
                dtstart=dtstart_aware,
                ignoretz=False,
            )
        except Exception as exc:
            self._logger.warning("Failed to parse RRULE: %s — %s", rrule_str, exc)
            return []

        uid = str(component.get("UID", ""))
        summary = str(component.get("SUMMARY", ""))
        location_val = component.get("LOCATION")
        location = {"displayName": str(location_val)} if location_val else None
        description = str(component.get("DESCRIPTION", ""))
        is_cancelled = str(component.get("STATUS", "")).upper() == "CANCELLED"
        tz_name = self._extract_tzname(dtstart_aware)

        results = []
        for occurrence in ruleset.between(start_dt, end_dt, inc=True):
            occ_end = occurrence + duration

            if is_all_day:
                occ_start_str = occurrence.strftime("%Y-%m-%dT00:00:00")
                occ_end_str = occ_end.strftime("%Y-%m-%dT00:00:00")
                occ_tz = self._config.get("timezone", "UTC")
            else:
                occ_start_str = occurrence.isoformat(timespec="seconds")
                occ_end_str = occ_end.isoformat(timespec="seconds")
                occ_tz = tz_name

            event_id = f"{uid}|{occ_start_str}"

            results.append({
                "id": event_id,
                "subject": summary,
                "start": {"dateTime": occ_start_str, "timeZone": occ_tz},
                "end": {"dateTime": occ_end_str, "timeZone": occ_tz},
                "location": location,
                "body": {"content": description},
                "isCancelled": is_cancelled,
                "isAllDay": is_all_day,
                "type": "singleInstance",
                "showAs": "busy",
                "seriesMasterId": None,
                "originalStart": None,
            })

        self._logger.debug(
            "Expanded RRULE '%s' → %d occurrences in window", summary, len(results)
        )
        return results

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

        # Re-compute start_str preserving offset when datetime is timezone-aware,
        # so _to_utc_iso receives the full "...T09:00:00-05:00" string and can
        # convert correctly to UTC instead of ignoring the offset.
        if not is_all_day and isinstance(dtstart_raw, datetime) and dtstart_raw.tzinfo is not None:
            start_str = dtstart_raw.isoformat(timespec="seconds")
        if not is_all_day and isinstance(dtend_raw, datetime) and dtend_raw.tzinfo is not None:
            end_str = dtend_raw.isoformat(timespec="seconds")

        location_val = event.get("LOCATION")
        location = {"displayName": str(location_val)} if location_val else None

        uid = str(event.get("UID", ""))
        event_id = f"{uid}|{start_str}"

        return {
            "id": event_id,
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
            # pytz zones expose .zone with the IANA name (e.g. "America/Bogota")
            if hasattr(dt.tzinfo, "zone"):
                return dt.tzinfo.zone
            name = dt.tzinfo.tzname(dt)
            if name:
                return name
        # Return empty string so _to_utc_iso falls back to config["timezone"]
        return ""

    @staticmethod
    def _dt_to_str(dt: datetime) -> str:
        return dt.strftime("%Y-%m-%dT%H:%M:%S")
