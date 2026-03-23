import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import load_config
from app.scheduler_rules import is_sync_allowed

OK = "✅"
FAIL = "❌"


def check(label: str, passed: bool, detail: str = "") -> bool:
    icon = OK if passed else FAIL
    suffix = f"  ({detail})" if detail else ""
    print(f"  {icon}  {label}{suffix}")
    return passed


def main() -> None:
    print("\n=== Calendar Sync — Setup Check ===\n")
    results = []

    # 1. OUTLOOK_ICS_URL definida
    ics_url = os.environ.get("OUTLOOK_ICS_URL", "")
    results.append(check("OUTLOOK_ICS_URL definida", bool(ics_url)))

    # 2. OUTLOOK_ICS_URL es una URL válida
    if ics_url:
        url_valid = ics_url.startswith("https://")
        results.append(check("OUTLOOK_ICS_URL empieza con https://", url_valid))

    # 3. GOOGLE_CREDENTIALS_JSON definida
    gcp_raw = os.environ.get("GOOGLE_CREDENTIALS_JSON", "")
    results.append(check("GOOGLE_CREDENTIALS_JSON definida", bool(gcp_raw)))

    # 4. GOOGLE_CREDENTIALS_JSON es JSON válido
    if gcp_raw:
        try:
            json.loads(gcp_raw)
            gcp_valid = True
        except json.JSONDecodeError as exc:
            gcp_valid = False
            results.append(check("GOOGLE_CREDENTIALS_JSON es JSON válido", False, str(exc)))
        if gcp_valid:
            results.append(check("GOOGLE_CREDENTIALS_JSON es JSON válido", True))

    # 5. config.json carga correctamente
    try:
        config = load_config()
        results.append(check("config.json cargado correctamente", True))

        print(f"\n  Timezone configurado : {config.get('timezone', 'N/A')}")

        # 6. Ventana horaria actual
        allowed = is_sync_allowed(config)
        label = "Sync permitido ahora"
        detail = "dentro de la ventana" if allowed else "fuera de la ventana"
        print(f"  {OK if allowed else FAIL}  {label}  ({detail})")

    except Exception as exc:
        results.append(check("config.json cargado correctamente", False, str(exc)))

    # Resumen
    all_ok = all(results)
    print("\n" + "=" * 36)
    if all_ok:
        print("  ✅  Listo para ejecutar")
    else:
        failed = results.count(False)
        print(f"  ❌  Faltan configuraciones ({failed} problema(s))")
    print("=" * 36 + "\n")

    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
