from datetime import datetime, timedelta

import pytz

from app.logger import get_logger


def is_sync_allowed(config: dict) -> bool:
    logger = get_logger()

    tz = pytz.timezone(config["timezone"])
    now_local = datetime.now(tz=tz)

    day_name = now_local.strftime("%A")
    current_time = now_local.strftime("%H:%M")

    schedule = config["schedule"]
    day_allowed = day_name in schedule["allowed_days"]
    time_allowed = schedule["allowed_hours_start"] <= current_time <= schedule["allowed_hours_end"]

    allowed = day_allowed and time_allowed
    logger.debug("Sync allowed: %s - Day: %s, Hour: %s", allowed, day_name, current_time)
    return allowed


def get_sync_window(config: dict) -> tuple[datetime, datetime]:
    now_utc = datetime.now(tz=pytz.utc)
    start_dt = now_utc - timedelta(days=config["sync_window_days_past"])
    end_dt = now_utc + timedelta(days=config["sync_window_days_future"])
    return start_dt, end_dt
