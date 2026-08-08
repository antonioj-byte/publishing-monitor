import './load-env';
import Parser from 'rss-parser';
import { createServerClient } from '../lib/supabase/server';

const parser = new Parser({
  timeout: 15_000,
  headers: { 'User-Agent': 'RSSMonitor/1.0 (internal scouting tool)' },
});

async function main() {
  const supabase = createServerClient();

  const { data: sources, error } = await supabase
    .from('sources')
    .select('id, name, rss_url, active')
    .eq('active', true)
    .order('name');

  if (error) throw error;
  if (!sources?.length) {
    console.log('No active sources found. Run seed-sources first.');
    return;
  }

  let ok = 0;
  let fail = 0;

  for (const source of sources) {
    try {
      const feed = await parser.parseURL(source.rss_url);
      const count = feed.items?.length ?? 0;
      console.log(`OK  ${source.name.padEnd(30)} ${count} items`);
      if (count > 0) ok++;
      else fail++;
    } catch (err) {
      console.log(`FAIL ${source.name.padEnd(30)} ${err instanceof Error ? err.message : err}`);
      fail++;
    }
  }

  console.log(`\n${ok}/${sources.length} feeds returned items`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
