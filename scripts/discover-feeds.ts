import fs from 'fs';
import path from 'path';
import Parser from 'rss-parser';
import { SEED_SOURCES } from './seed-data';

const USER_AGENT = 'RSSMonitor/1.0 (internal scouting tool)';
const TIMEOUT_MS = 10_000;
const COMMON_PATHS = ['/feed', '/rss', '/rss.xml', '/feed.xml', '/atom.xml', '/rss_full.xml'];

export interface DiscoveredFeed {
  domain: string;
  name: string;
  site_url: string;
  rss_url: string | null;
  method: 'override' | 'link-tag' | 'common-path' | 'failed';
  item_count: number;
  error?: string;
}

const parser = new Parser({
  timeout: TIMEOUT_MS,
  headers: { 'User-Agent': USER_AGENT },
});

async function fetchText(url: string): Promise<string> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);

  try {
    const res = await fetch(url, {
      headers: { 'User-Agent': USER_AGENT },
      signal: controller.signal,
      redirect: 'follow',
    });

    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }

    return await res.text();
  } finally {
    clearTimeout(timer);
  }
}

function resolveUrl(base: string, href: string): string {
  return new URL(href, base).toString();
}

function findRssLink(html: string, baseUrl: string): string | null {
  const patterns = [
    /<link[^>]+type=["']application\/rss\+xml["'][^>]+href=["']([^"']+)["']/gi,
    /<link[^>]+href=["']([^"']+)["'][^>]+type=["']application\/rss\+xml["']/gi,
    /<link[^>]+type=["']application\/atom\+xml["'][^>]+href=["']([^"']+)["']/gi,
    /<link[^>]+href=["']([^"']+)["'][^>]+type=["']application\/atom\+xml["']/gi,
  ];

  for (const pattern of patterns) {
    const match = pattern.exec(html);
    if (match?.[1]) {
      return resolveUrl(baseUrl, match[1]);
    }
  }

  return null;
}

async function validateFeed(rssUrl: string): Promise<number> {
  const feed = await parser.parseURL(rssUrl);
  return feed.items?.length ?? 0;
}

async function discoverOne(source: (typeof SEED_SOURCES)[number]): Promise<DiscoveredFeed> {
  const base: DiscoveredFeed = {
    domain: source.domain,
    name: source.name,
    site_url: source.site_url,
    rss_url: null,
    method: 'failed',
    item_count: 0,
  };

  if (source.rss_url) {
    try {
      const count = await validateFeed(source.rss_url);
      return {
        ...base,
        rss_url: source.rss_url,
        method: 'override',
        item_count: count,
      };
    } catch (err) {
      return {
        ...base,
        method: 'failed',
        error: err instanceof Error ? err.message : String(err),
      };
    }
  }

  const pageUrl = source.discover_url ?? source.site_url;

  try {
    const html = await fetchText(pageUrl);
    const linkTagUrl = findRssLink(html, pageUrl);

    if (linkTagUrl) {
      const count = await validateFeed(linkTagUrl);
      return {
        ...base,
        rss_url: linkTagUrl,
        method: 'link-tag',
        item_count: count,
      };
    }
  } catch (err) {
    // fall through to common paths
  }

  const origin = new URL(pageUrl).origin;

  for (const suffix of COMMON_PATHS) {
    const candidates = [
      `${origin}${suffix}`,
      `${pageUrl.replace(/\/$/, '')}${suffix}`,
    ];

    for (const candidate of candidates) {
      try {
        const count = await validateFeed(candidate);
        if (count > 0) {
          return {
            ...base,
            rss_url: candidate,
            method: 'common-path',
            item_count: count,
          };
        }
      } catch {
        // try next path
      }
    }
  }

  return {
    ...base,
    method: 'failed',
    error: 'No RSS feed detected via link tag or common paths',
  };
}

async function main() {
  const results: DiscoveredFeed[] = [];

  for (const source of SEED_SOURCES) {
    process.stdout.write(`Discovering ${source.domain}... `);
    const result = await discoverOne(source);
    results.push(result);
    console.log(result.rss_url ? `${result.method} (${result.item_count} items)` : 'FAILED');
  }

  const outputDir = path.join(__dirname, 'output');
  fs.mkdirSync(outputDir, { recursive: true });
  const outputPath = path.join(outputDir, 'discovered-feeds.json');
  fs.writeFileSync(outputPath, JSON.stringify(results, null, 2));

  const failed = results.filter((r) => !r.rss_url);
  const ok = results.filter((r) => r.rss_url);

  console.log('\n--- Summary ---');
  console.log(`Found: ${ok.length}/${results.length}`);
  console.log(`Output: ${outputPath}`);

  if (failed.length > 0) {
    console.log('\nSources without detectable RSS (manual action needed):');
    console.table(
      failed.map((f) => ({
        domain: f.domain,
        name: f.name,
        error: f.error ?? 'unknown',
      })),
    );
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
