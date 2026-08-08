# Publishing Monitor

Agregador interno de señales del sector del libro. Ingesta RSS, clasificación con Claude, dashboard filtrable.

## Setup

### 1. Supabase

1. Crear proyecto en [supabase.com](https://supabase.com) (región EU recomendada).
2. Ejecutar el SQL de [`supabase/migrations/001_initial_schema.sql`](supabase/migrations/001_initial_schema.sql) en el SQL Editor.
3. Copiar credenciales a `.env.local`:

```bash
cp .env.example .env.local
# Rellenar SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_ROLE_KEY
# También ANTHROPIC_API_KEY y CRON_SECRET (string aleatorio)
```

Para el dashboard en cliente, duplica URL y anon key con prefijo `NEXT_PUBLIC_`.

### 2. Instalar y verificar

```bash
npm install
npm run smoke-db          # Verifica conexión DB
npm run discover-feeds    # Descubre feeds RSS
npm run seed-sources      # Inserta fuentes en DB
npm run test-feeds        # Valida que los feeds parsean
npm run dev
```

### 3. Ingesta y clasificación (local)

```bash
curl -H "Authorization: Bearer $CRON_SECRET" http://localhost:3000/api/cron/ingest
curl -H "Authorization: Bearer $CRON_SECRET" http://localhost:3000/api/cron/classify
```

## Deploy (Vercel)

1. Push a GitHub e importar en Vercel.
2. Configurar las mismas env vars.
3. Los crons en `vercel.json` se activan en producción (requiere plan Pro para frecuencia <1/día; alternativa: cron-job.org con Bearer token).

## Scripts

| Comando | Descripción |
|---------|-------------|
| `npm run discover-feeds` | Busca RSS en dominios semilla |
| `npm run seed-sources` | Inserta fuentes en Supabase |
| `npm run test-feeds` | Valida feeds activos |
| `npm run smoke-db` | Test de conexión DB |
| `npm run validate-mvp` | Comprueba criterios MVP contra Supabase |

## Fuentes semilla

23 dominios en `scripts/seed-data.ts`. Tras discovery + overrides manuales, **19 fuentes** tienen RSS válido (≥15 requerido). Cuatro sin feed detectable: Publishers Weekly, The Bookseller, Shelf Awareness, Publishers Marketplace — ver `DEPLOY.md`.

## Arquitectura

- **Ingesta** (`/api/cron/ingest`): cada 2h, parsea RSS y deduplica por URL.
- **Clasificación** (`/api/cron/classify`): cada hora, Claude puntúa items sin score.
- **Dashboard** (`/`): filtros por categoría/región, orden por fecha o relevancia.
- **Export** (`/api/export/week`): markdown agrupado por categoría para newsletter.
