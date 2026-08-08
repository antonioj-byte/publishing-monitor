import './load-env';
import { createServerClient } from '../lib/supabase/server';

async function main() {
  const supabase = createServerClient();

  const [sources, items, classified, recentItems, recentClassified] = await Promise.all([
    supabase.from('sources').select('*', { count: 'exact', head: true }).eq('active', true),
    supabase.from('items').select('*', { count: 'exact', head: true }),
    supabase.from('items').select('*', { count: 'exact', head: true }).not('relevance_score', 'is', null),
    supabase
      .from('items')
      .select('*', { count: 'exact', head: true })
      .gte('fetched_at', new Date(Date.now() - 48 * 60 * 60 * 1000).toISOString()),
    supabase
      .from('items')
      .select('*', { count: 'exact', head: true })
      .gte('fetched_at', new Date(Date.now() - 48 * 60 * 60 * 1000).toISOString())
      .not('relevance_score', 'is', null),
  ]);

  const activeSources = sources.count ?? 0;
  const totalItems = items.count ?? 0;
  const classifiedItems = classified.count ?? 0;
  const recent = recentItems.count ?? 0;
  const recentOk = recentClassified.count ?? 0;
  const classifyRate = totalItems > 0 ? ((classifiedItems / totalItems) * 100).toFixed(1) : '0';
  const recentRate = recent > 0 ? ((recentOk / recent) * 100).toFixed(1) : 'N/A';

  console.log('=== MVP Validation ===\n');
  console.log(`Active sources:     ${activeSources} ${activeSources >= 15 ? '✓' : '✗ (need ≥15)'}`);
  console.log(`Total items:        ${totalItems}`);
  console.log(`Classified items:   ${classifiedItems} (${classifyRate}%)`);
  console.log(`Last 48h items:     ${recent}`);
  console.log(`Last 48h classified: ${recentOk} (${recentRate}%) ${recent > 0 && recentOk / recent >= 0.9 ? '✓' : recent > 0 ? '✗ (need ≥90%)' : ''}`);
}

main().catch((err) => {
  console.error(err.message);
  process.exit(1);
});
