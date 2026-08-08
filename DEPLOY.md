# Deploy checklist

## Pre-requisitos

- [ ] Proyecto Supabase creado y migración SQL ejecutada
- [ ] `.env.local` configurado localmente
- [ ] `npm run smoke-db` pasa
- [ ] `npm run discover-feeds && npm run seed-sources` inserta ≥15 fuentes
- [ ] `npm run test-feeds` confirma feeds parseables

## Vercel

1. Importar repo en [vercel.com/new](https://vercel.com/new)
2. Framework preset: **Next.js**
3. Environment variables (Production + Preview):

| Variable | Notas |
|----------|-------|
| `SUPABASE_URL` | Project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | Solo server-side |
| `SUPABASE_ANON_KEY` | Dashboard read |
| `NEXT_PUBLIC_SUPABASE_URL` | Mismo que SUPABASE_URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Mismo que anon key |
| `ANTHROPIC_API_KEY` | Clasificación IA |
| `CRON_SECRET` | String aleatorio ≥32 chars |

4. Deploy. Los crons en `vercel.json` se registran automáticamente en producción.

### Plan Vercel y crons

- **Pro plan**: crons cada 2h/1h funcionan nativamente.
- **Hobby plan**: límite de 1 cron/día. Alternativa gratuita: [cron-job.org](https://cron-job.org) con:
  - URL: `https://tu-dominio.vercel.app/api/cron/ingest`
  - Header: `Authorization: Bearer <CRON_SECRET>`
  - Repetir para `/api/cron/classify`

## Validación post-deploy (48h)

```bash
# Ingesta manual
curl -H "Authorization: Bearer $CRON_SECRET" https://tu-dominio.vercel.app/api/cron/ingest

# Clasificación manual
curl -H "Authorization: Bearer $CRON_SECRET" https://tu-dominio.vercel.app/api/cron/classify

# Export semanal
curl "https://tu-dominio.vercel.app/api/export/week?min_score=3" -o semana.md
```

### Criterios MVP

| Criterio | Query / check |
|----------|---------------|
| ≥15 fuentes activas | Supabase: `select count(*) from sources where active = true` |
| Ingesta estable 48h | Vercel logs sin crash; `items` crece |
| Clasificación ≥90% | `select count(*) filter (where relevance_score is not null)::float / count(*) from items where fetched_at > now() - interval '48 hours'` |
| Dashboard + export | Abrir `/` y descargar export |

## Fuentes sin RSS (acción manual)

Estas fuentes no tienen feed detectable. Opciones: RSS.app, descartar, o añadir override en `scripts/seed-data.ts`:

- publishersweekly.com
- thebookseller.com
- shelf-awareness.com
- publishersmarketplace.com
