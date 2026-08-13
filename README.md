# Bot editorial Telegram

Bot local que ingiere RSS y scraping de medios culturales/editoriales, clasifica con Claude y envía un informe diario por Telegram.

## Requisitos

- Python 3.11+
- Cuenta Anthropic (API key)
- Bot de Telegram (`TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID`)

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Editar .env con tus claves
```

## Inicialización

```bash
python scripts/init_db.py
python scripts/load_medios.py
```

## Uso manual

```bash
# Ingesta única
python scripts/run_ingest_once.py

# Validar deduplicación (2 pasadas)
python scripts/validate_ingest.py

# Clasificar pendientes
python scripts/classify_pending.py

# Ver informe de prueba
python scripts/print_report.py
```

## Bot + scheduler

```bash
python -m bot.main
```

Tareas programadas (hora `Europe/Madrid`):

- **Ingesta**: 08:00, 11:00, 14:00, 17:00, 20:00, 23:00
- **Cierre**: 06:00 (ingesta + clasificación)
- **Informe automático**: 06:30

Comandos Telegram:

- `/informe` — desde último cierre o últimas 24h
- `/informe_hoy` — solo lo recopilado hoy

## Estructura

| Ruta | Descripción |
|------|-------------|
| `medios.csv` | Fuentes con categoría `ideas`/`noticias` y método `rss`/`scraping` |
| `ingest/` | RSS (feedparser) y scraping (BeautifulSoup) |
| `ai/classify.py` | Clasificación y resumen con Anthropic |
| `reports/generator.py` | Formato del informe Telegram |
| `bot/main.py` | APScheduler + bot polling |

## Medios

~100 fuentes en `medios.csv`: prensa generalista (secciones cultura/libros), revistas de ensayo, semanarios y medios especializados del sector editorial.

Los medios sin RSS usan scraping de la sección concreta (Fase 7).
