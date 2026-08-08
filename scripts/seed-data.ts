import type { SourceCategory, Region } from '../lib/types';

export interface SeedSource {
  domain: string;
  name: string;
  site_url: string;
  category: SourceCategory;
  region: Region;
  language: string;
  /** If set, skip discovery and use this RSS URL directly */
  rss_url?: string;
  /** Page to scan for RSS link tags when not using rss_url override */
  discover_url?: string;
  notes?: string;
}

export const SEED_SOURCES: SeedSource[] = [
  // Industry
  {
    domain: 'publishersweekly.com',
    name: 'Publishers Weekly',
    site_url: 'https://www.publishersweekly.com/pw/by-topic/industry-news',
    category: 'industry',
    region: 'us',
    language: 'en',
    notes: 'Sin RSS público detectable — requiere RSS.app o descartar',
  },
  {
    domain: 'thebookseller.com',
    name: 'The Bookseller',
    site_url: 'https://www.thebookseller.com',
    category: 'industry',
    region: 'uk',
    language: 'en',
    notes: 'Sin RSS general — solo feeds por tag/taxonomy',
  },
  {
    domain: 'livreshebdo.fr',
    name: 'Livres Hebdo',
    site_url: 'https://www.livreshebdo.fr',
    category: 'industry',
    region: 'eu',
    language: 'fr',
  },
  {
    domain: 'boersenblatt.net',
    name: 'Börsenblatt',
    site_url: 'https://www.boersenblatt.net',
    category: 'industry',
    region: 'eu',
    language: 'de',
  },
  {
    domain: 'publishingperspectives.com',
    name: 'Publishing Perspectives',
    site_url: 'https://publishingperspectives.com',
    category: 'industry',
    region: 'us',
    language: 'en',
  },
  {
    domain: 'shelf-awareness.com',
    name: 'Shelf Awareness',
    site_url: 'https://www.shelf-awareness.com',
    category: 'industry',
    region: 'us',
    language: 'en',
    notes: 'Sin RSS detectable — newsletter por email',
  },
  {
    domain: 'publishersmarketplace.com',
    name: 'Publishers Marketplace',
    site_url: 'https://www.publishersmarketplace.com',
    category: 'industry',
    region: 'us',
    language: 'en',
    notes: 'RSS limitado en free tier — /feed/ devuelve 404; requiere RSS.app',
  },

  // Press
  {
    domain: 'theguardian.com',
    name: 'The Guardian Books',
    site_url: 'https://www.theguardian.com/books',
    rss_url: 'https://www.theguardian.com/books/rss',
    category: 'press',
    region: 'uk',
    language: 'en',
  },
  {
    domain: 'nytimes.com',
    name: 'NYT Books',
    site_url: 'https://www.nytimes.com/section/books',
    rss_url: 'https://rss.nytimes.com/services/xml/rss/nyt/Books.xml',
    category: 'press',
    region: 'us',
    language: 'en',
  },
  {
    domain: 'washingtonpost.com',
    name: 'Washington Post Books',
    site_url: 'https://www.washingtonpost.com/entertainment/books/',
    rss_url: 'https://feeds.washingtonpost.com/rss/entertainment/books',
    category: 'press',
    region: 'us',
    language: 'en',
  },
  {
    domain: 'lemonde.fr',
    name: 'Le Monde des Livres',
    site_url: 'https://www.lemonde.fr/livres/',
    rss_url: 'https://www.lemonde.fr/livres/rss_full.xml',
    category: 'press',
    region: 'eu',
    language: 'fr',
  },
  {
    domain: 'elpais.com',
    name: 'El País Babelia',
    site_url: 'https://elpais.com/babelia/',
    rss_url: 'https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/section/babelia/portada',
    category: 'press',
    region: 'eu',
    language: 'es',
  },
  {
    domain: 'lavanguardia.com',
    name: 'La Vanguardia Cultura',
    site_url: 'https://www.lavanguardia.com/cultura',
    rss_url: 'https://www.lavanguardia.com/rss/cultura.xml',
    category: 'press',
    region: 'eu',
    language: 'es',
  },
  {
    domain: 'repubblica.it',
    name: 'Repubblica Cultura',
    site_url: 'https://www.repubblica.it/cultura/',
    discover_url: 'https://www.repubblica.it/cultura/',
    category: 'press',
    region: 'eu',
    language: 'it',
  },

  // Essay
  {
    domain: 'lithub.com',
    name: 'Literary Hub',
    site_url: 'https://lithub.com',
    rss_url: 'https://lithub.com/feed',
    category: 'essay',
    region: 'us',
    language: 'en',
  },
  {
    domain: 'theparisreview.org',
    name: 'The Paris Review Blog',
    site_url: 'https://www.theparisreview.org/blog',
    rss_url: 'https://www.theparisreview.org/blog/feed',
    category: 'essay',
    region: 'us',
    language: 'en',
  },
  {
    domain: 'nplusonemag.com',
    name: 'n+1',
    site_url: 'https://www.nplusonemag.com',
    category: 'essay',
    region: 'us',
    language: 'en',
  },
  {
    domain: 'thepointmag.com',
    name: 'The Point',
    site_url: 'https://thepointmag.com',
    category: 'essay',
    region: 'us',
    language: 'en',
  },
  {
    domain: 'granta.com',
    name: 'Granta',
    site_url: 'https://granta.com',
    discover_url: 'https://granta.com/articles/',
    category: 'essay',
    region: 'uk',
    language: 'en',
  },
  {
    domain: 'lrb.co.uk',
    name: 'London Review of Books',
    site_url: 'https://www.lrb.co.uk',
    rss_url: 'https://www.lrb.co.uk/feeds/rss',
    category: 'essay',
    region: 'uk',
    language: 'en',
  },
  {
    domain: 'nybooks.com',
    name: 'New York Review of Books',
    site_url: 'https://www.nybooks.com',
    discover_url: 'https://www.nybooks.com/articles/',
    category: 'essay',
    region: 'us',
    language: 'en',
  },
  {
    domain: 'worldliteraturetoday.org',
    name: 'World Literature Today',
    site_url: 'https://worldliteraturetoday.org',
    category: 'essay',
    region: 'us',
    language: 'en',
  },
  {
    domain: 'jacobin.com',
    name: 'Jacobin Culture',
    site_url: 'https://jacobin.com/culture',
    discover_url: 'https://jacobin.com/culture',
    category: 'essay',
    region: 'us',
    language: 'en',
  },
];
