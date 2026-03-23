from datetime import datetime

import pytz

from app.config import load_config
from app.google_client import GoogleCalendarClient
from app.logger import get_logger
from app.outlook_client import OutlookClient
from app.scheduler_rules import get_sync_window, is_sync_allowed
from app.state_store import (
    get_fingerprint,
    get_google_event_id,
    load_state,
    remove_event_mapping,
    save_state,
    set_event_mapping,
    set_fingerprint,
)
from app.transformers import compute_fingerprint, internal_to_google, outlook_to_internal


def run_sync() -> None:
    try:
        # PASO 1 — Cargar configuración y estado
        config = load_config()
        logger = get_logger()
        state = load_state()

        # PASO 2 — Verificar ventana horaria
        if not is_sync_allowed(config):
            logger.info("Sync skipped: outside allowed schedule window")
            return

        # PASO 3 — Inicializar clientes
        outlook = OutlookClient(config)
        google = GoogleCalendarClient(config)

        # PASO 4 — Obtener eventos de Outlook
        start_dt, end_dt = get_sync_window(config)
        raw_events = outlook.get_calendar_events(start_dt, end_dt)
        logger.info("Fetched %d events from Outlook", len(raw_events))

        # PASO 5 — Procesar cada evento
        counters = {"created": 0, "updated": 0, "deleted": 0, "ignored": 0, "skipped": 0}

        for raw_event in raw_events:
            # a. Convertir al modelo interno
            internal = outlook_to_internal(raw_event, config)
            if internal is None:
                counters["skipped"] += 1
                continue

            # b-d. Fingerprint y mapping actuales
            new_fingerprint = compute_fingerprint(internal)
            old_fingerprint = get_fingerprint(internal["event_key"], state)
            google_id = get_google_event_id(internal["outlook_id"], state)

            # e. Lógica de decisión
            if internal["is_cancelled"]:
                if google_id and config["behavior"].get("delete_cancelled_events", True):
                    google.delete_event(google_id)
                    state = remove_event_mapping(internal["outlook_id"], state)
                    logger.info("DELETED: %s", internal["title"])
                    counters["deleted"] += 1
                continue

            if google_id is None:
                google_body = internal_to_google(internal, config)
                new_google_id = google.create_event(google_body)
                if new_google_id:
                    state = set_event_mapping(internal["outlook_id"], new_google_id, state)
                    state = set_fingerprint(internal["event_key"], new_fingerprint, state)
                    logger.info("CREATED: %s", internal["title"])
                    counters["created"] += 1

            elif new_fingerprint != old_fingerprint:
                google_body = internal_to_google(internal, config)
                google.update_event(google_id, google_body)
                state = set_fingerprint(internal["event_key"], new_fingerprint, state)
                logger.info("UPDATED: %s", internal["title"])
                counters["updated"] += 1

            else:
                logger.debug("IGNORED (no changes): %s", internal["title"])
                counters["ignored"] += 1

        # PASO 6 — Guardar estado y loguear resumen
        state["last_run"] = datetime.now(tz=pytz.utc).isoformat()
        save_state(state)
        logger.info(
            "Sync complete — created: %d, updated: %d, deleted: %d, "
            "ignored: %d, skipped: %d",
            counters["created"],
            counters["updated"],
            counters["deleted"],
            counters["ignored"],
            counters["skipped"],
        )

    except Exception:
        get_logger().exception("Sync failed with unhandled error")
        raise


if __name__ == "__main__":
    run_sync()
