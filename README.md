# calendar-sync

Sincronización autónoma de eventos Office 365 → Google Calendar vía GitHub Actions.
Se ejecuta cada 10 minutos, detecta cambios por fingerprint y solo toca lo necesario.

## Arquitectura

```
GitHub Actions (cron 10min)
        ↓
    sync.py (orquestador)
        ↓
OutlookClient → eventos crudos
        ↓
transformers.py → modelo interno + fingerprint
        ↓
state_store.py → comparar con estado anterior
        ↓
GoogleCalendarClient → CREATE / UPDATE / DELETE / IGNORE
```

## Lógica de sincronización

- Ventana: últimos 7 días + próximos 60 días
- Evento nuevo → CREATE en Google Calendar
- Evento modificado (fingerprint distinto) → UPDATE
- Evento cancelado → DELETE (si delete_cancelled_events=true)
- Sin cambios → IGNORED (no toca la API de Google)
- Eventos privados → ignorados (configurable)

## Requisitos previos

1. **Azure AD** — App registration con permisos delegados Calendars.Read
2. **Google Cloud** — Service account con Google Calendar API habilitada

## Configuración

### 1. Clonar y configurar
```bash
git clone https://github.com/juanjo-geo/calendar-sync.git
cd calendar-sync
pip install -r requirements.txt
```

### 2. Editar data/config.json
Reemplazar `YOUR_TENANT_ID` y `YOUR_CLIENT_ID` con los valores reales de Azure AD.

### 3. Configurar GitHub Secrets
En Settings → Secrets and variables → Actions, agregar:
- `MICROSOFT_CLIENT_SECRET`
- `GOOGLE_CREDENTIALS_JSON` (JSON completo del service account, en una sola línea)

### 4. Verificar configuración
```bash
export MICROSOFT_CLIENT_SECRET="..."
export GOOGLE_CREDENTIALS_JSON='{"type":"service_account",...}'
python scripts/setup_check.py
```

## Ejecución local
```bash
export MICROSOFT_CLIENT_SECRET="..."
export GOOGLE_CREDENTIALS_JSON='{"type":"service_account",...}'
python -m app.sync
```

## Ejecución automática
GitHub Actions ejecuta el workflow cada 10 minutos.
El sistema valida internamente si está dentro de la ventana horaria permitida
definida en `config.json → schedule`.

## Tests
```bash
python -m pytest tests/ -v
```
25 tests — cobertura de config, state, scheduler, transformers e integración.

## Seguridad
- Las credenciales NUNCA van en el repositorio
- `data/state.json` está en `.gitignore`
- Usar siempre GitHub Secrets para credenciales en producción

## Estructura

```
calendar-sync/
├── app/
│   ├── sync.py              # Orquestador principal
│   ├── config.py            # Carga y validación de configuración
│   ├── logger.py            # Logger singleton con salida a consola y archivo
│   ├── state_store.py       # Persistencia de estado (mappings + fingerprints)
│   ├── outlook_client.py    # Cliente Microsoft Graph API
│   ├── google_client.py     # Cliente Google Calendar API
│   ├── transformers.py      # Conversión de formatos + fingerprint
│   └── scheduler_rules.py  # Ventana horaria y rango de sync
├── data/
│   ├── config.json          # Configuración del proyecto (sin secretos)
│   └── state.json           # Estado de sync (en .gitignore)
├── tests/
│   ├── test_transformers.py        # Tests de config, state y transformers
│   ├── test_scheduler_rules.py     # Tests de reglas horarias
│   └── test_integration_smoke.py  # Smoke test del ciclo completo
├── scripts/
│   └── setup_check.py       # Diagnóstico de configuración
├── .github/workflows/
│   └── sync.yml             # Workflow de GitHub Actions (cron 10min)
├── .env.example             # Plantilla de variables de entorno
├── .gitignore
└── requirements.txt
```
