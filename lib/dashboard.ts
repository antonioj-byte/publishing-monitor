import { createServerClient } from '@/lib/supabase/server';
import type { ItemWithSource, SourceCategory, Region } from '@/lib/types';

export interface DashboardFilters {
  category?: string;
  region?: string;
  sort?: 'date' | 'relevance';
}

export async function getDashboardData(filters: DashboardFilters) {
  const supabase = createServerClient();

  let query = supabase
    .from('items')
    .select('*, sources!inner(name, category, region)')
    .limit(100);

  if (filters.category && filters.category !== 'all') {
    query = query.eq('sources.category', filters.category);
  }
  if (filters.region && filters.region !== 'all') {
    query = query.eq('sources.region', filters.region);
  }

  if (filters.sort === 'relevance') {
    query = query.order('relevance_score', { ascending: false, nullsFirst: false });
    query = query.order('published_at', { ascending: false });
  } else {
    query = query.order('published_at', { ascending: false });
  }

  const [itemsResult, sourcesCount, itemsCount] = await Promise.all([
    query,
    supabase.from('sources').select('*', { count: 'exact', head: true }).eq('active', true),
    supabase.from('items').select('*', { count: 'exact', head: true }),
  ]);

  if (itemsResult.error) throw itemsResult.error;

  const items: ItemWithSource[] = (itemsResult.data ?? []).map((row) => {
    const source = (Array.isArray(row.sources) ? row.sources[0] : row.sources) as {
      name: string;
      category: SourceCategory;
      region: Region;
    };

    return {
      id: row.id,
      source_id: row.source_id,
      title: row.title,
      url: row.url,
      summary: row.summary,
      published_at: row.published_at,
      fetched_at: row.fetched_at,
      relevance_score: row.relevance_score,
      ai_summary_es: row.ai_summary_es,
      ai_tags: row.ai_tags,
      source_name: source.name,
      source_category: source.category,
      source_region: source.region,
    };
  });

  return {
    items,
    activeSources: sourcesCount.count ?? 0,
    totalItems: itemsCount.count ?? 0,
  };
}
