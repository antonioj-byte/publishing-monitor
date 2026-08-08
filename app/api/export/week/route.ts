import { NextRequest, NextResponse } from 'next/server';
import { createServerClient } from '@/lib/supabase/server';
import type { ItemWithSource, SourceCategory } from '@/lib/types';

const CATEGORY_ORDER: SourceCategory[] = ['industry', 'press', 'essay'];
const CATEGORY_LABELS: Record<SourceCategory, string> = {
  industry: 'Industry',
  press: 'Press',
  essay: 'Essay',
};

function formatDate(date: string | null): string {
  if (!date) return 'sin fecha';
  return new Date(date).toISOString().slice(0, 10);
}

export async function GET(request: NextRequest) {
  const { searchParams } = request.nextUrl;
  const category = searchParams.get('category');
  const region = searchParams.get('region');
  const minScore = parseInt(searchParams.get('min_score') ?? '3', 10);

  const weekAgo = new Date();
  weekAgo.setDate(weekAgo.getDate() - 7);

  const supabase = createServerClient();

  let query = supabase
    .from('items')
    .select('*, sources!inner(name, category, region)')
    .gte('published_at', weekAgo.toISOString())
    .gte('relevance_score', minScore)
    .order('relevance_score', { ascending: false })
    .order('published_at', { ascending: false });

  if (category && category !== 'all') {
    query = query.eq('sources.category', category);
  }
  if (region && region !== 'all') {
    query = query.eq('sources.region', region);
  }

  const { data, error } = await query;

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }

  const items: ItemWithSource[] = (data ?? []).map((row) => {
    const source = (Array.isArray(row.sources) ? row.sources[0] : row.sources) as {
      name: string;
      category: SourceCategory;
      region: ItemWithSource['source_region'];
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

  const today = new Date().toISOString().slice(0, 10);
  const weekStart = weekAgo.toISOString().slice(0, 10);

  const lines: string[] = [
    `# Señales editorial — semana del ${weekStart} al ${today}`,
    '',
  ];

  for (const cat of CATEGORY_ORDER) {
    const group = items.filter((i) => i.source_category === cat);
    if (group.length === 0) continue;

    lines.push(`## ${CATEGORY_LABELS[cat]}`, '');

    group.forEach((item, idx) => {
      const tags = item.ai_tags?.length ? item.ai_tags.join(', ') : '—';
      lines.push(
        `${idx + 1}. **${item.title}** — ${item.source_name} (${formatDate(item.published_at)})`,
        `   ${item.ai_summary_es ?? item.summary ?? '(sin resumen)'}`,
        `   Tags: ${tags}`,
        `   ${item.url}`,
        '',
      );
    });
  }

  if (items.length === 0) {
    lines.push('_No hay señales que cumplan los filtros esta semana._');
  }

  const markdown = lines.join('\n');

  return new NextResponse(markdown, {
    headers: {
      'Content-Type': 'text/markdown; charset=utf-8',
      'Content-Disposition': `attachment; filename="senal-editorial-${today}.md"`,
    },
  });
}
