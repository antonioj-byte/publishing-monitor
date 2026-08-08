import type { ItemWithSource } from '@/lib/types';

const CATEGORY_COLORS: Record<string, string> = {
  industry: 'bg-amber-100 text-amber-800',
  press: 'bg-blue-100 text-blue-800',
  essay: 'bg-violet-100 text-violet-800',
};

const SCORE_COLORS: Record<number, string> = {
  5: 'bg-emerald-100 text-emerald-800',
  4: 'bg-green-100 text-green-800',
  3: 'bg-yellow-100 text-yellow-800',
  2: 'bg-orange-100 text-orange-800',
  1: 'bg-stone-100 text-stone-600',
};

function formatRelative(date: string | null): string {
  if (!date) return 'sin fecha';
  const d = new Date(date);
  return d.toLocaleDateString('es-ES', { day: 'numeric', month: 'short', year: 'numeric' });
}

export function ItemCard({ item }: { item: ItemWithSource }) {
  const scoreClass =
    item.relevance_score != null
      ? SCORE_COLORS[item.relevance_score] ?? SCORE_COLORS[1]
      : 'bg-stone-100 text-stone-500';

  return (
    <article className="rounded-lg border border-stone-200 bg-white p-5 shadow-sm">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${CATEGORY_COLORS[item.source_category]}`}>
          {item.source_category}
        </span>
        <span className="rounded-full bg-stone-100 px-2 py-0.5 text-xs text-stone-600">
          {item.source_region.toUpperCase()}
        </span>
        <span className="text-xs text-stone-500">{item.source_name}</span>
        <span className="text-xs text-stone-400">·</span>
        <span className="text-xs text-stone-500">{formatRelative(item.published_at)}</span>
        <span className={`ml-auto rounded-full px-2 py-0.5 text-xs font-semibold ${scoreClass}`}>
          {item.relevance_score != null ? `${item.relevance_score}/5` : 'pendiente IA'}
        </span>
      </div>

      <h2 className="mb-2 text-lg font-semibold leading-snug">
        <a
          href={item.url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-stone-900 hover:text-stone-600 hover:underline"
        >
          {item.title}
        </a>
      </h2>

      {(item.ai_summary_es || item.summary) && (
        <p className="mb-3 text-sm leading-relaxed text-stone-600">
          {item.ai_summary_es ?? item.summary}
        </p>
      )}

      {item.ai_tags && item.ai_tags.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {item.ai_tags.map((tag) => (
            <span
              key={tag}
              className="rounded bg-stone-100 px-2 py-0.5 text-xs text-stone-600"
            >
              {tag}
            </span>
          ))}
        </div>
      )}
    </article>
  );
}
