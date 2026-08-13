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

## Medios con paywall — alternativas

| Medio | Problema | Alternativa |
|-------|----------|-------------|
| **Financial Times Books** | Scraping 403 | RSS oficial: `https://www.ft.com/books?format=rss` |
| **Wall Street Journal Books** | Scraping 401; feeds Dow Jones con API key | Google News RSS (`site:wsj.com book review`) |
| **The Times Books** | Sin RSS; scraping mezcla secciones | Google News RSS (`site:thetimes.com culture books review`) |
| **Washington Post Books** | Feed directo vacío | Google News RSS (`site:washingtonpost.com/entertainment/books`) |
| **The Globe and Mail Books** | `/arts/books/rss/` roto | Google News RSS (`site:theglobeandmail.com/arts/books`) |
| **Granta** | `granta.com/feed/` devuelve HTML | Substack oficial: `https://grantamag.substack.com/feed` |

Detalle en [`ingest/paywall_alternatives.py`](ingest/paywall_alternatives.py).

Verificar feeds:

```bash
python scripts/test_paywall_feeds.py
```

**Nota:** Los feeds de Google News enlazan vía `news.google.com` (redirección al artículo). Es la vía estándar cuando el medio no publica RSS público.
