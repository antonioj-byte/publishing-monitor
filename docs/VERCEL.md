# Vercel — desactivar despliegues

Este proyecto es un **bot Python local** (Telegram + SQLite). **No debe desplegarse en Vercel.**

El archivo [`vercel.json`](vercel.json) incluye `ignoreCommand` para que cada push cancele el build automáticamente y dejes de recibir emails de error.

## Opción recomendada: desconectar Vercel por completo

Así dejas de consumir cuota y no recibes ningún email:

1. Entra en [vercel.com/dashboard](https://vercel.com/dashboard)
2. Abre el proyecto **publishing-monitor**
3. **Settings** → **Git** → **Disconnect** (o elimina el proyecto entero)

## Si prefieres mantener el proyecto en Vercel

Con `vercel.json` actual, los despliegues se marcan como **cancelados** (no como error). Puede que sigas recibiendo notificaciones de “deployment skipped”.

Para silenciarlas: **Settings** → **Notifications** → desactiva emails de deploy para este proyecto.

## ¿Por qué pasaba?

El repo empezó como Next.js + Supabase desplegado en Vercel. Tras migrar a Python local, Vercel seguía intentando `npm run build` en cada push y fallaba.
