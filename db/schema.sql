CREATE TABLE IF NOT EXISTS medios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL UNIQUE,
    url_site TEXT NOT NULL,
    url_rss TEXT,
    url_scraping TEXT,
    metodo TEXT NOT NULL CHECK (metodo IN ('rss', 'scraping')),
    categoria_default TEXT NOT NULL CHECK (categoria_default IN ('ideas', 'noticias')),
    idioma TEXT NOT NULL,
    region TEXT NOT NULL CHECK (region IN ('eu', 'us', 'uk', 'latam', 'ca', 'apac')),
    activo INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS articulos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    medio_id INTEGER NOT NULL REFERENCES medios(id),
    url TEXT NOT NULL UNIQUE,
    titulo_original TEXT NOT NULL,
    fecha_publicacion TEXT,
    fecha_ingesta TEXT NOT NULL DEFAULT (datetime('now')),
    categoria TEXT NOT NULL CHECK (categoria IN ('ideas', 'noticias')),
    idioma TEXT NOT NULL,
    resumen_raw TEXT,
    resumen_generado TEXT,
    titular_traducido TEXT,
    relevance_score INTEGER,
    hash_contenido TEXT NOT NULL UNIQUE,
    procesado INTEGER NOT NULL DEFAULT 0,
    enviado INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_articulos_fecha_ingesta ON articulos (fecha_ingesta DESC);
CREATE INDEX IF NOT EXISTS idx_articulos_procesado ON articulos (procesado) WHERE procesado = 0;
CREATE INDEX IF NOT EXISTS idx_articulos_categoria ON articulos (categoria);
CREATE INDEX IF NOT EXISTS idx_articulos_enviado ON articulos (enviado);

CREATE TABLE IF NOT EXISTS informes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha_cierre TEXT NOT NULL,
    tipo TEXT NOT NULL CHECK (tipo IN ('automatico', 'manual')),
    articulos_incluidos TEXT NOT NULL,
    enviado_at TEXT NOT NULL DEFAULT (datetime('now'))
);
