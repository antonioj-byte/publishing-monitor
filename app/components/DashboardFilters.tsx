'use client';

import { useRouter, useSearchParams } from 'next/navigation';

export function DashboardFilters() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const category = searchParams.get('category') ?? 'all';
  const region = searchParams.get('region') ?? 'all';
  const sort = searchParams.get('sort') ?? 'date';

  function update(key: string, value: string) {
    const params = new URLSearchParams(searchParams.toString());
    if (value === 'all' && (key === 'category' || key === 'region')) {
      params.delete(key);
    } else {
      params.set(key, value);
    }
    router.push(`/?${params.toString()}`);
  }

  return (
    <div className="flex flex-wrap gap-3 items-end">
      <label className="flex flex-col gap-1 text-sm">
        <span className="text-stone-500">Categoría</span>
        <select
          value={category}
          onChange={(e) => update('category', e.target.value)}
          className="rounded-md border border-stone-300 bg-white px-3 py-2 text-sm"
        >
          <option value="all">Todas</option>
          <option value="industry">Industry</option>
          <option value="press">Press</option>
          <option value="essay">Essay</option>
        </select>
      </label>

      <label className="flex flex-col gap-1 text-sm">
        <span className="text-stone-500">Región</span>
        <select
          value={region}
          onChange={(e) => update('region', e.target.value)}
          className="rounded-md border border-stone-300 bg-white px-3 py-2 text-sm"
        >
          <option value="all">Todas</option>
          <option value="eu">EU</option>
          <option value="us">US</option>
          <option value="uk">UK</option>
          <option value="latam">LATAM</option>
        </select>
      </label>

      <label className="flex flex-col gap-1 text-sm">
        <span className="text-stone-500">Orden</span>
        <select
          value={sort}
          onChange={(e) => update('sort', e.target.value)}
          className="rounded-md border border-stone-300 bg-white px-3 py-2 text-sm"
        >
          <option value="date">Fecha</option>
          <option value="relevance">Relevancia</option>
        </select>
      </label>

      <a
        href={`/api/export/week?${searchParams.toString()}`}
        className="rounded-md bg-stone-900 px-4 py-2 text-sm text-white hover:bg-stone-700"
      >
        Exportar semana
      </a>
    </div>
  );
}
