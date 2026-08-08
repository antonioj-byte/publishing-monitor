import Parser from 'rss-parser';
import { createServerClient } from '@/lib/supabase/server';
import type { IngestResult, Source } from '@/lib/types';

const parser = new Parser({
  timeout: 20_000,
  headers: { 'User-Agent': 'RSSMonitor/1.0 (internal scouting tool)' },
});

function asString(value: unknown): string | null {
  if (typeof value === 'string') return value;
  if (value && typeof value === 'object' && '$' in value && typeof (value as { $: unknown }).$ === 'object') {
    const href = (value as { $: { href?: string } }).$?.href;
    if (href) return href;
  }
  if (value && typeof value === 'object' && 'href' in value && typeof (value as { href: unknown }).href === 'string') {
    return (value as { href: string }).href;
  }
  return null;
}

function stripHtml(html: string): string {
  return html.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();
}

function normalizeUrl(url: string): string {
  try {
    const parsed = new URL(url);
    parsed.hash = '';
    let normalized = parsed.toString();
    if (normalized.endsWith('/') && parsed.pathname !== '/') {
      normalized = normalized.slice(0, -1);
    }
    return normalized;
  } catch {
    return url;
  }
}

function toSummary(item: Parser.Item): string | null {
  const raw = item.contentSnippet || item.summary || item.content;
  if (!raw || typeof raw !== 'string') return null;
  const text = stripHtml(raw);
  return text.length > 500 ? `${text.slice(0, 497)}...` : text;
}

function toPublishedAt(item: Parser.Item): string | null {
  const date = item.isoDate || item.pubDate;
  if (!date) return null;
  const parsed = new Date(date);
  return Number.isNaN(parsed.getTime()) ? null : parsed.toISOString();
}

export async function ingestAllSources(): Promise<IngestResult> {
  const supabase = createServerClient();
  const result: IngestResult = { inserted: 0, skipped: 0, errors: [] };

  const { data: sources, error } = await supabase
    .from('sources')
    .select('*')
    .eq('active', true);

  if (error) throw error;

  for (const source of (sources ?? []) as Source[]) {
    try {
      const feed = await parser.parseURL(source.rss_url);

      for (const item of feed.items ?? []) {
        const title = asString(item.title);
        const link = asString(item.link);
        if (!title || !link) continue;

        const row = {
          source_id: source.id,
          title: title.trim(),
          url: normalizeUrl(link),
          summary: toSummary(item),
          published_at: toPublishedAt(item),
        };

        const { data, error: insertError } = await supabase
          .from('items')
          .insert(row)
          .select('id')
          .maybeSingle();

        if (insertError) {
          if (insertError.code === '23505') {
            result.skipped++;
          } else {
            throw insertError;
          }
        } else if (data) {
          result.inserted++;
        }
      }
    } catch (err) {
      result.errors.push({
        sourceId: source.id,
        sourceName: source.name,
        error: err instanceof Error ? err.message : String(err),
      });
    }
  }

  return result;
}
