# Crons gratuitos con cron-job.org (plan Hobby Vercel)

Vercel Hobby solo permite 1 cron/día. Para ingesta cada 2h y clasificación cada 1h, usa [cron-job.org](https://cron-job.org) (gratis).

## Job 1 — Ingesta RSS (cada 2 horas)

- **URL:** `https://TU-DOMINIO.vercel.app/api/cron/ingest`
- **Schedule:** cada 2 horas (o `0 */2 * * *`)
- **Request method:** GET
- **Headers:**
  - `Authorization`: `Bearer TU_CRON_SECRET`

## Job 2 — Clasificación IA (cada hora)

- **URL:** `https://TU-DOMINIO.vercel.app/api/cron/classify`
- **Schedule:** cada hora (o `30 * * * *`)
- **Request method:** GET
- **Headers:**
  - `Authorization`: `Bearer TU_CRON_SECRET`

## Probar manualmente

```bash
curl -H "Authorization: Bearer TU_CRON_SECRET" https://TU-DOMINIO.vercel.app/api/cron/ingest
curl -H "Authorization: Bearer TU_CRON_SECRET" https://TU-DOMINIO.vercel.app/api/cron/classify
```

Reemplaza `TU-DOMINIO` y `TU_CRON_SECRET` con los valores de Vercel env vars / `.env.local`.
