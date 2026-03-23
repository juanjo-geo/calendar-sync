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

    # 1. MICROSOFT_CLIENT_SECRET
    ms_secret = os.environ.get("MICROSOFT_CLIENT_SECRET", "")
    results.append(check("MICROSOFT_CLIENT_SECRET definida", bool(ms_secret)))

    # 2. GOOGLE_CREDENTIALS_JSON definida
    gcp_raw = os.environ.get("GOOGLE_CREDENTIALS_JSON", "")
    results.append(check("GOOGLE_CREDENTIALS_JSON definida", bool(gcp_raw)))

    # 3. GOOGLE_CREDENTIALS_JSON es JSON válido
    gcp_valid = False
    if gcp_raw:
        try:
            json.loads(gcp_raw)
            gcp_valid = True
        except json.JSONDecodeError as exc:
            results.append(check("GOOGLE_CREDENTIALS_JSON es JSON válido", False, str(exc)))
    if gcp_raw:
        results.append(check("GOOGLE_CREDENTIALS_JSON es JSON válido", gcp_valid))

    # 4-5. config.json con valores reales
    try:
        config = load_config()
        ms = config.get("microsoft", {})

        tenant_ok = ms.get("tenant_id", "") != "YOUR_TENANT_ID"
        results.append(check("tenant_id configurado (no placeholder)", tenant_ok))

        client_ok = ms.get("client_id", "") != "YOUR_CLIENT_ID"
        results.append(check("client_id configurado (no placeholder)", client_ok))

        print(f"\n  Timezone configurado : {config.get('timezone', 'N/A')}")

        allowed = is_sync_allowed(config)
        print(f"  Sync permitido ahora : {OK if allowed else FAIL}  ({allowed})")

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
