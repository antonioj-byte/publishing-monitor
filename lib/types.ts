export type SourceCategory = 'industry' | 'press' | 'essay';
export type Region = 'eu' | 'us' | 'uk' | 'latam';

export interface Source {
  id: string;
  name: string;
  site_url: string;
  rss_url: string;
  category: SourceCategory;
  region: Region;
  language: string;
  active: boolean;
}

export interface Item {
  id: string;
  source_id: string;
  title: string;
  url: string;
  summary: string | null;
  published_at: string | null;
  fetched_at: string;
  relevance_score: number | null;
  ai_summary_es: string | null;
  ai_tags: string[] | null;
}

export interface ItemWithSource extends Item {
  source_name: string;
  source_category: SourceCategory;
  source_region: Region;
}

export interface IngestResult {
  inserted: number;
  skipped: number;
  errors: Array<{ sourceId: string; sourceName: string; error: string }>;
}

export interface ClassifyResult {
  classified: number;
  failed: number;
  remaining: number;
}

export interface ClassificationOutput {
  relevance_score: number;
  ai_summary_es: string;
  ai_tags: string[];
}
