# Bot editorial Telegram

Bot local que ingiere RSS y scraping de medios culturales/editoriales, clasifica con Claude y envía un informe diario por Telegram.

## Inicio rápido

```bash
chmod +x scripts/setup.sh deploy/*.sh
./scripts/setup.sh
```

Edita `.env` con tus claves, luego:

```bash
python3 scripts/get_telegram_chat_id.py   # tras enviar /start al bot
python3 scripts/run_ingest_once.py
python3 scripts/reclassify_all.py --yes     # reclasifica todo con Claude
python3 scripts/print_report.py             # vista previa
python3 -m bot.main                         # arrancar
```

## Configuración (`.env`)

Copia la plantilla:

```bash
cp .env.example .env
```

| Variable | Dónde obtenerla |
|----------|-----------------|
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com/) → API Keys |
| `TELEGRAM_BOT_TOKEN` | Telegram → @BotFather → `/newbot` |
| `TELEGRAM_CHAT_ID` | Envía `/start` al bot → `python scripts/get_telegram_chat_id.py` |

## Requisitos

- Python 3.11+
- Cuenta Anthropic (API key)
- Bot de Telegram

## Scripts útiles

| Comando | Descripción |
|---------|-------------|
| `scripts/setup.sh` | Instala deps, init DB, carga medios |
| `scripts/run_ingest_once.py` | Ingesta manual de todos los medios |
| `scripts/classify_pending.py` | Clasifica solo artículos nuevos |
| `scripts/reclassify_all.py --yes` | Reset + reclasifica **todos** con Claude |
| `scripts/print_report.py` | Informe de prueba en terminal |
| `scripts/get_telegram_chat_id.py` | Obtiene tu chat ID de Telegram |
| `scripts/test_paywall_feeds.py` | Verifica feeds alternativos (FT, WSJ, etc.) |

## Bot + scheduler

```bash
python -m bot.main
```

Tareas programadas (hora `Europe/Madrid`):

- **Ingesta**: 08:00, 11:00, 14:00, 17:00, 20:00, 23:00
- **Cierre**: 06:00 (ingesta + clasificación)
- **Informe automático**: 06:30

Comandos Telegram: `/informe`, `/informe_hoy`, `/start`

## Arranque automático

**Linux (systemd):**

```bash
./deploy/install-systemd.sh
sudo journalctl -u editorial-bot -f
```

**macOS (LaunchAgent):**

```bash
./deploy/install-launchd.sh
tail -f data/bot.log
```

El servicio lee variables desde `.env` (macOS vía `deploy/run-bot.sh` generado en la instalación).

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
