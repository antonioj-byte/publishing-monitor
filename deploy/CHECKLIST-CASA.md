# Checklist — montar el bot 24/7 en Railway (desde casa)

Tiempo estimado: **20–30 minutos**. Solo navegador + Telegram en el móvil.

## Antes de empezar — ten a mano

Abre tu `.env` del proyecto (o anota estos tres valores):

- `ANTHROPIC_API_KEY` (empieza por `sk-ant-...`)
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID` (tu número, ej. `1141602138`)

## Paso 1 — Parar otras copias del bot

Solo **una** instancia puede usar el token.

- Si tienes el Mac con el bot: ciérralo o no arranques `Arrancar-Bot.command`.
- El bot de Cursor cloud dejará de usarse cuando Railway esté activo.

## Paso 2 — Cuenta Railway

1. Abre **https://railway.app** en el Mac.
2. **Login with GitHub**.
3. Autoriza acceso al repo `antonioj-byte/publishing-monitor`.

## Paso 3 — Crear el proyecto

1. **New Project** → **Deploy from GitHub repo**.
2. Elige **publishing-monitor** (rama `main`).
3. Railway detecta el `Dockerfile` y empieza a construir (5–10 min la primera vez).

## Paso 4 — Variables de entorno

En el servicio → pestaña **Variables** → **Add Variable** (o Raw Editor):

```
ANTHROPIC_API_KEY=pega_tu_clave
TELEGRAM_BOT_TOKEN=pega_tu_token
TELEGRAM_CHAT_ID=pega_tu_chat_id
DATABASE_PATH=/app/data/editorial.db
TIMEZONE=Europe/Madrid
```

Guarda. Railway redeployará solo.

## Paso 5 — Volumen (obligatorio)

Sin esto pierdes la base de datos en cada actualización.

Railway **no** pone el volumen dentro del servicio en el menú lateral. Hazlo así:

**Opción A — atajo (Mac):**
1. En el proyecto Railway, pulsa **`⌘ + K`** (Command + K).
2. Escribe **`New Volume`** o **`Volume`**.
3. Elige tu servicio (el del bot).
4. **Mount path:** `/app/data` (no uses `/app` solo — borraría el código).
5. Tamaño: **1 GB**.

**Opción B — clic derecho:**
1. En la vista del proyecto (canvas con cajas), **clic derecho en el espacio vacío**.
2. **Create Volume** / **New Volume**.
3. Conecta al servicio del bot → mount path **`/app/data`**.

**Opción C — dentro del servicio (si tu UI lo muestra):**
1. Abre el servicio → **Settings** → busca **Volumes** → **Add Volume**.

Tras crearlo, redeploy (o espera el siguiente deploy automático).

## Paso 6 — Comprobar logs

1. Pestaña **Deployments** → el último deploy → **View logs**.
2. Busca:
   - `Polling activo — bot listo` → **OK**
   - `Primera arrancada: inicializando base de datos` → normal la primera vez

## Paso 7 — Probar desde el iPhone

En Telegram, al bot `@publishersnewsmonitorbot`:

1. `/ping` → debe responder `pong`
2. `/informe_hoy` → puede tardar 1–3 min la primera vez (ingesta + clasificación)

## Paso 8 — Listo para vacaciones

- Puedes **apagar el Mac** o llevártelo.
- Solo necesitas **Telegram** en el iPhone.
- Informe automático: **06:30** (hora Madrid), si Railway sigue activo.

---

## Si algo falla

| Problema | Qué hacer |
|----------|-----------|
| No responde `/ping` | Revisa Variables (token y chat ID). Mira Logs. |
| Error 409 / conflicto | Para bot en Mac; redeploy en Railway. |
| Informe vacío al principio | Normal: espera 1–2 h a que ingiera feeds, o pide `/informe` al día siguiente. |
| Crash por memoria | En Railway → Settings → sube RAM a **1 GB**. |

## Coste mensual orientativo

- **Railway (servidor):** ~5–10 €
- **Anthropic (API):** ~5–15 € según uso
- **Telegram:** gratis

Revisa gasto API en https://console.anthropic.com

## Volver al Mac después

1. Railway → **Stop** o pause el servicio.
2. En el Mac: doble clic **`deploy/Arrancar-Bot.command`**.

Guía extendida: [DEPLOY-CLOUD.md](./DEPLOY-CLOUD.md)
