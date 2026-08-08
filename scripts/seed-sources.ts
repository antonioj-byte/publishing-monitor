import './load-env';
import fs from 'fs';
import path from 'path';
import { createServerClient } from '../lib/supabase/server';
import { SEED_SOURCES } from './seed-data';
import type { DiscoveredFeed } from './discover-feeds';

async function main() {
  const supabase = createServerClient();
  const discoveredPath = path.join(__dirname, 'output', 'discovered-feeds.json');

  let discovered: DiscoveredFeed[] = [];
  if (fs.existsSync(discoveredPath)) {
    discovered = JSON.parse(fs.readFileSync(discoveredPath, 'utf-8'));
  }

  const discoveredByDomain = new Map(discovered.map((d) => [d.domain, d]));
  let inserted = 0;
  let skipped = 0;
  const failed: string[] = [];

  for (const source of SEED_SOURCES) {
    const found = discoveredByDomain.get(source.domain);
    const rssUrl = source.rss_url ?? found?.rss_url;

    if (!rssUrl) {
      failed.push(source.domain);
      console.warn(`SKIP ${source.domain}: no RSS URL`);
      continue;
    }

    const { error } = await supabase.from('sources').upsert(
      {
        name: source.name,
        site_url: source.site_url,
        rss_url: rssUrl,
        category: source.category,
        region: source.region,
        language: source.language,
        active: true,
      },
      { onConflict: 'rss_url' },
    );

    if (error) {
      console.error(`ERROR ${source.domain}:`, error.message);
      failed.push(source.domain);
    } else {
      inserted++;
      console.log(`OK ${source.name} → ${rssUrl}`);
    }
  }

  const { count } = await supabase
    .from('sources')
    .select('*', { count: 'exact', head: true })
    .eq('active', true);

  console.log('\n--- Seed Summary ---');
  console.log(`Upserted: ${inserted}`);
  console.log(`Skipped/failed: ${failed.length}`);
  console.log(`Active sources in DB: ${count ?? 0}`);

  if (failed.length > 0) {
    console.log('Failed domains:', failed.join(', '));
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
