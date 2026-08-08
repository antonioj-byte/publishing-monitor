import { createServerClient } from '@/lib/supabase/server';
import { classifyItem, sleep } from '@/lib/ai/classify-item';
import type { ClassifyResult, SourceCategory, Region } from '@/lib/types';

const BATCH_SIZE = 20;
const DELAY_MS = 200;

export async function classifyBatch(): Promise<ClassifyResult> {
  const supabase = createServerClient();
  const result: ClassifyResult = { classified: 0, failed: 0, remaining: 0 };

  const { data: items, error } = await supabase
    .from('items')
    .select('id, title, summary, source_id, sources(name, category, region)')
    .is('relevance_score', null)
    .order('published_at', { ascending: false })
    .limit(BATCH_SIZE);

  if (error) throw error;

  for (const item of items ?? []) {
    const rawSource = item.sources;
    const source = (Array.isArray(rawSource) ? rawSource[0] : rawSource) as {
      name: string;
      category: SourceCategory;
      region: Region;
    } | null;

    if (!source) {
      result.failed++;
      continue;
    }

    try {
      const classification = await classifyItem({
        title: item.title,
        summary: item.summary,
        sourceName: source.name,
        category: source.category,
        region: source.region,
      });

      const { error: updateError } = await supabase
        .from('items')
        .update({
          relevance_score: classification.relevance_score,
          ai_summary_es: classification.ai_summary_es,
          ai_tags: classification.ai_tags,
        })
        .eq('id', item.id);

      if (updateError) throw updateError;
      result.classified++;
    } catch (err) {
      console.error(`Classify failed for item ${item.id}:`, err);
      result.failed++;
    }

    await sleep(DELAY_MS);
  }

  const { count } = await supabase
    .from('items')
    .select('*', { count: 'exact', head: true })
    .is('relevance_score', null);

  result.remaining = count ?? 0;
  return result;
}
