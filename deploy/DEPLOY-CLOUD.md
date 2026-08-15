# Despliegue 24/7 en la nube (vacaciones, solo iPhone)

El bot en Telegram funciona desde el móvil, pero **el proceso del bot** debe estar en un servidor encendido permanentemente. Esta guía usa **Railway** (la más sencilla, sin terminal) o **Fly.io** (alternativa).

## Antes de empezar

1. Para el bot en Cursor cloud y en tu Mac (solo **una** instancia puede usar el token):
   - Cierra sesiones cloud / para procesos locales si los tienes.
2. Ten a mano tu `.env` con:
   - `GOOGLE_API_KEY` (recomendado, ~10× más barato) o `ANTHROPIC_API_KEY`
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`

## Opción recomendada: Railway (interfaz web)

### 1. Cuenta y proyecto

1. Entra en [railway.app](https://railway.app) y crea cuenta (GitHub).
2. **New Project** → **Deploy from GitHub repo** → elige `publishing-monitor`.
3. Railway detectará el `Dockerfile` y construirá la imagen.

### 2. Variables de entorno

En el servicio → **Variables**, añade (copia de tu `.env`):

| Variable | Obligatoria |
|----------|-------------|
| `GOOGLE_API_KEY` + `CLASSIFY_PROVIDER=gemini` | Sí (recomendado, más barato) |
| `GEMINI_MODEL` | Opcional (`gemini-2.5-flash` por defecto) |
| `GEMINI_FALLBACK_MODEL` | Opcional (`gemini-3.1-flash-lite`; no uses `gemini-2.5-flash-lite`) |
| `ANTHROPIC_API_KEY` | Alternativa a Gemini |
| `TELEGRAM_BOT_TOKEN` | Sí |
| `TELEGRAM_CHAT_ID` | Sí |
| `DATABASE_PATH` | `/app/data/editorial.db` |
| `TIMEZONE` | `Europe/Madrid` |
| `CLASSIFY_BEFORE_TELEGRAM_REPORT` | `0` (default): informes Telegram rápidos; clasificación en cron `:15`. `1`: clasifica ~20 pendientes antes del informe. |

Opcional: `MAX_DESTACADOS`, `MAX_RELEVANTES`, `MAX_SECUNDARIOS`, `MAX_ARTICLES_PER_MEDIO`.

### 3. Volumen persistente (importante)

Sin volumen pierdes la base de datos en cada redeploy.

Railway crea volúmenes **desde el canvas del proyecto**, no siempre dentro del servicio:

1. **`⌘ + K`** (Mac) o **Ctrl + K** → escribe **New Volume**  
   **o** clic derecho en el espacio vacío del canvas → **Create Volume**
2. Conecta el volumen al servicio del bot.
3. **Mount path:** **`/app/data`** (nunca `/app` a secas)
4. Tamaño mínimo (1 GB basta).

### 4. Desplegar

1. **Memoria (importante):** en el servicio → **Settings** → **Resources** → asigna **≥ 1 GB RAM**. Con menos, el modelo de embeddings puede provocar *Deploy Ran Out of Memory*.
2. **Deploy** (automático al push, o manual).
3. Revisa **Logs**: debe aparecer `Polling activo — bot listo`.
4. En Telegram: **`/ping`**.

### 5. Coste orientativo

Railway cobra por uso (~5–10 €/mes para un bot pequeño con volumen). Consulta su pricing actual.

---

## Alternativa: Fly.io (terminal mínima)

Requiere instalar [flyctl](https://fly.io/docs/hands-on/install-flyctl/) una vez.

```bash
cd publishing-monitor
fly auth login
fly apps create TU-NOMBRE-UNICO-BOT   # edita fly.toml con ese nombre
fly volumes create editorial_data --region cdg --size 1
fly secrets set ANTHROPIC_API_KEY=sk-ant-... TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_ID=...
fly deploy
fly logs
```

Región `cdg` (París) es cercana a España. Memoria: 1 GB (embeddings).

---

## VPS Linux (DigitalOcean, Hetzner, etc.)

Si ya tienes un servidor Ubuntu:

```bash
git clone https://github.com/antonioj-byte/publishing-monitor.git
cd publishing-monitor
cp .env.example .env   # edita con tus claves
docker compose up -d
```

O sin Docker:

```bash
./scripts/setup.sh
./deploy/install-systemd.sh
```

---

## Comprobar que sigue vivo

Desde Telegram: **`/ping`** (debe responder al instante).

Para descargar la base de datos SQLite sin terminal: **`/descargar_db`** (te envía el archivo `.db`).

Para acceso por terminal al contenedor (no `railway shell`, que es local):

```bash
ssh-keygen -t ed25519 -C "tu@email.com"
# Sube la clave pública en railway.com → Settings → SSH Keys
railway ssh
ls -lh /app/data/editorial.db
```

Informes automáticos: **06:30** (Europe/Madrid), si el servidor está activo.

## Problemas frecuentes

| Síntoma | Causa | Solución |
|---------|-------|----------|
| No responde nada | Dos bots con el mismo token | Para Mac/Cursor; deja solo Railway/Fly |
| Informe vacío al inicio | BD nueva sin ingesta | Espera 1–2 h o ejecuta ingesta manual en logs |
| OOM / *Deploy Ran Out of Memory* | RAM insuficiente en **build** (pip + modelo embeddings en Dockerfile) o en **runtime** | Quita prewarm del build (PR #43+). Runtime: **Settings → Resources → 1 GB** mínimo. No lances `/reclasificar` y `/informe` a la vez justo tras reiniciar |

## Volver al Mac después de vacaciones

```bash
# Para el servicio cloud en Railway/Fly (dashboard → stop)
./deploy/Arrancar-Bot.command
```
