import hashlib
import json
from datetime import datetime

import pytz

from app.logger import get_logger


def outlook_to_internal(raw_event: dict, config: dict) -> dict | None:
    """Converts a raw Graph API event dict to the internal model.
    Returns None if the event should be skipped (private and sync_private_events=False).
    """
    logger = get_logger()

    # Skip private events when configured
    sensitivity = raw_event.get("sensitivity", "normal")
    if sensitivity == "private" and not config["behavior"].get("sync_private_events", False):
        logger.debug("Skipping private event: %s", raw_event.get("id"))
        return None

    outlook_id = raw_event["id"]
    is_all_day = raw_event.get("isAllDay", False)
    event_type = raw_event.get("type", "singleInstance")
    series_master_id = raw_event.get("seriesMasterId")
    is_cancelled = raw_event.get("isCancelled", False)

    start_raw = raw_event.get("start", {})
    end_raw = raw_event.get("end", {})

    if is_all_day:
        start_str = start_raw.get("dateTime", "")[:10]  # "YYYY-MM-DD"
        end_str = end_raw.get("dateTime", "")[:10]
        original_start = raw_event.get("originalStart", "")[:10] if raw_event.get("originalStart") else None
    else:
        start_str = _to_utc_iso(start_raw.get("dateTime", ""), start_raw.get("timeZone"), config)
        end_str = _to_utc_iso(end_raw.get("dateTime", ""), end_raw.get("timeZone"), config)
        original_start_raw = raw_event.get("originalStart")
        original_start = _to_utc_iso(original_start_raw, None, config) if original_start_raw else None

    # Build event_key: composite for recurring instances, plain id for single events
    if series_master_id and original_start:
        event_key = f"{series_master_id}|{original_start}"
    else:
        event_key = outlook_id

    description = raw_event.get("bodyPreview") or raw_event.get("body", {}).get("content")
    location_obj = raw_event.get("location", {})
    location = location_obj.get("displayName") if location_obj else None

    return {
        "outlook_id": outlook_id,
        "event_key": event_key,
        "title": raw_event.get("subject", "(No title)"),
        "start": start_str,
        "end": end_str,
        "location": location or None,
        "description": description or None,
        "is_cancelled": is_cancelled,
        "is_all_day": is_all_day,
        "series_master_id": series_master_id,
        "original_start": original_start,
        "event_type": event_type,
    }


def internal_to_google(internal: dict, config: dict) -> dict:
    """Converts an internal model dict to a Google Calendar event body."""
    is_all_day = internal["is_all_day"]

    if is_all_day:
        start = {"date": internal["start"]}
        end = {"date": internal["end"]}
    else:
        start = {"dateTime": internal["start"], "timeZone": "UTC"}
        end = {"dateTime": internal["end"], "timeZone": "UTC"}

    description = internal.get("description") or ""
    if config["behavior"].get("add_sync_tag_to_description", False):
        tag = config["behavior"].get("sync_tag", "[Sync: Outlook]")
        if tag not in description:
            description = f"{description}\n\n{tag}".strip() if description else tag

    event_body: dict = {
        "summary": internal["title"],
        "start": start,
        "end": end,
        "description": description or None,
    }

    if internal.get("location"):
        event_body["location"] = internal["location"]

    # Remove keys with None values — Google API rejects null fields
    return {k: v for k, v in event_body.items() if v is not None}


def compute_fingerprint(internal: dict) -> str:
    """Returns a stable SHA-256 fingerprint of the fields that matter for change detection."""
    payload = {
        "title": internal.get("title"),
        "start": internal.get("start"),
        "end": internal.get("end"),
        "location": internal.get("location"),
        "description": internal.get("description"),
        "is_all_day": internal.get("is_all_day"),
        "is_cancelled": internal.get("is_cancelled"),
    }
    serialized = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(serialized.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _to_utc_iso(dt_str: str, tz_hint: str | None, config: dict) -> str:
    """Parses a datetime string and returns an ISO 8601 UTC string.

    Handles three cases:
    - String with explicit offset or Z  → parse directly as aware, convert to UTC
    - String without offset + valid tz_hint → localize with tz_hint, convert to UTC
    - String without offset + missing/unknown tz_hint → localize with config timezone
    """
    if not dt_str:
        return ""

    # Detect whether the string already carries explicit timezone info
    has_z = dt_str.endswith("Z")
    has_offset = False
    if "T" in dt_str:
        time_part = dt_str.split("T", 1)[1]
        has_offset = "+" in time_part or time_part.count("-") > 0

    if has_z or has_offset:
        # Parse as timezone-aware directly — do NOT re-localize
        try:
            from dateutil import parser as dateutil_parser
            aware_dt = dateutil_parser.parse(dt_str)
            return aware_dt.astimezone(pytz.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            pass  # fall through to naive parsing

    # Naive string — pick timezone: tz_hint if valid, otherwise config timezone
    tz_name = tz_hint or config.get("timezone", "UTC")
    try:
        local_tz = pytz.timezone(tz_name)
    except pytz.UnknownTimeZoneError:
        # tz_hint not recognized by pytz (e.g. "COT", "-05:00") — use config timezone
        local_tz = pytz.timezone(config.get("timezone", "UTC"))

    # Strip any leftover offset markers before parsing as naive
    base = dt_str.rstrip("Z")
    if "T" in base:
        date_part, time_part = base.split("T", 1)
        for sep in ("+", "-"):
            if sep in time_part:
                time_part = time_part.split(sep)[0]
                break
        base = f"{date_part}T{time_part}"

    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
        try:
            naive_dt = datetime.strptime(base, fmt)
            break
        except ValueError:
            continue
    else:
        get_logger().warning("Could not parse datetime string: %s", dt_str)
        return dt_str

    aware_dt = local_tz.localize(naive_dt, is_dst=False)
    utc_dt = aware_dt.astimezone(pytz.utc)
    return utc_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
