from dataclasses import dataclass
from typing import Literal

Categoria = Literal["ideas", "noticias"]
Metodo = Literal["rss", "scraping"]
Region = Literal["eu", "us", "uk", "latam", "ca", "apac"]


@dataclass
class ReportFilter:
    days: int | None = None
    pais: str | None = None
    region: str | None = None
    location_label: str | None = None
    tags: list[str] | None = None
    tag_labels: list[str] | None = None


@dataclass
class Medio:
    id: int
    nombre: str
    url_site: str
    url_rss: str | None
    url_scraping: str | None
    metodo: Metodo
    categoria_default: Categoria
    idioma: str
    region: Region
    pais: str
    tier: int
    activo: bool


@dataclass
class Articulo:
    id: int
    medio_id: int
    url: str
    titulo_original: str
    fecha_publicacion: str | None
    fecha_ingesta: str
    categoria: Categoria
    idioma: str
    resumen_raw: str | None
    resumen_generado: str | None
    titular_traducido: str | None
    relevance_score: int | None
    hash_contenido: str
    procesado: bool
    enviado: bool
    tags: str | None = None
    medio_nombre: str | None = None
    medio_region: Region | None = None
