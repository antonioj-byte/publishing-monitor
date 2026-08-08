import './load-env';
import { createServerClient } from '../lib/supabase/server';

async function main() {
  const supabase = createServerClient();

  const { data: source, error: sourceError } = await supabase
    .from('sources')
    .insert({
      name: 'Smoke Test Source',
      site_url: 'https://example.com',
      rss_url: `https://example.com/feed-smoke-${Date.now()}`,
      category: 'industry',
      region: 'us',
      language: 'en',
      active: false,
    })
    .select()
    .single();

  if (sourceError) throw sourceError;

  const { data: item, error: itemError } = await supabase
    .from('items')
    .insert({
      source_id: source.id,
      title: 'Smoke Test Item',
      url: `https://example.com/smoke-${Date.now()}`,
      summary: 'Test summary',
      published_at: new Date().toISOString(),
    })
    .select()
    .single();

  if (itemError) throw itemError;

  const { data: readBack, error: readError } = await supabase
    .from('items')
    .select('*, sources(name)')
    .eq('id', item.id)
    .single();

  if (readError) throw readError;

  console.log('Smoke test OK:', {
    sourceId: source.id,
    itemId: item.id,
    joinedSource: readBack.sources,
  });

  await supabase.from('items').delete().eq('id', item.id);
  await supabase.from('sources').delete().eq('id', source.id);
}

main().catch((err) => {
  console.error('Smoke test failed:', err.message);
  process.exit(1);
});
