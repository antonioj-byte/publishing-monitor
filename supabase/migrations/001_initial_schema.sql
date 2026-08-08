create table sources (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  site_url text not null,
  rss_url text not null,
  category text not null check (category in ('industry','press','essay')),
  region text not null check (region in ('eu','us','uk','latam')),
  language text not null,
  active boolean default true
);

create table items (
  id uuid primary key default gen_random_uuid(),
  source_id uuid references sources(id),
  title text not null,
  url text not null unique,
  summary text,
  published_at timestamptz,
  fetched_at timestamptz default now(),
  relevance_score int,
  ai_summary_es text,
  ai_tags text[]
);

create index items_published_at_idx on items (published_at desc);
create index items_relevance_score_idx on items (relevance_score desc nulls last);
create index items_source_id_idx on items (source_id);
create index items_unclassified_idx on items (published_at desc) where relevance_score is null;

create unique index sources_rss_url_idx on sources (rss_url);
