import { Suspense } from 'react';
import { getDashboardData } from '@/lib/dashboard';
import { DashboardFilters } from './components/DashboardFilters';
import { ItemCard } from './components/ItemCard';

interface PageProps {
  searchParams: { category?: string; region?: string; sort?: string };
}

export default async function Home({ searchParams }: PageProps) {
  const sort = searchParams.sort === 'relevance' ? 'relevance' : 'date';

  let data;
  let error: string | null = null;

  try {
    data = await getDashboardData({
      category: searchParams.category,
      region: searchParams.region,
      sort,
    });
  } catch (err) {
    error = err instanceof Error ? err.message : 'Error loading dashboard';
    data = { items: [], activeSources: 0, totalItems: 0 };
  }

  return (
    <div className="min-h-screen bg-stone-50">
      <header className="border-b border-stone-200 bg-white">
        <div className="mx-auto max-w-4xl px-4 py-6">
          <h1 className="text-2xl font-bold text-stone-900">Scouting Editorial</h1>
          <p className="mt-1 text-sm text-stone-500">
            Inteligencia de mercado del sector del libro
          </p>
          <div className="mt-3 flex gap-4 text-sm text-stone-600">
            <span>{data.totalItems} artículos</span>
            <span>·</span>
            <span>{data.activeSources} fuentes activas</span>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-4xl px-4 py-6">
        <Suspense fallback={<div className="mb-6 h-10 animate-pulse rounded bg-stone-200" />}>
          <DashboardFilters />
        </Suspense>

        {error && (
          <div className="mt-6 rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-700">
            {error}. Configura Supabase en <code>.env.local</code> y ejecuta la migración SQL.
          </div>
        )}

        <div className="mt-6 space-y-4">
          {data.items.length === 0 && !error && (
            <p className="text-center text-stone-500 py-12">
              No hay artículos todavía. Ejecuta la ingesta con{' '}
              <code className="rounded bg-stone-200 px-1">npm run discover-feeds</code> y el cron de ingesta.
            </p>
          )}

          {data.items.map((item) => (
            <ItemCard key={item.id} item={item} />
          ))}
        </div>
      </main>
    </div>
  );
}
