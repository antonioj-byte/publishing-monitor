# Criterios editoriales

Personaliza este archivo. El clasificador LLM lo lee automáticamente.

## Prioridad 1 — Cuándo subir relevance_score

### Convergencia mediática
Si varios medios cubren el **mismo tema, autor o libro**, es señal importante.
En el informe diario, estos casos aparecen en la sección **📡 En varios medios**.

### Actualidad y recencia
- Prioriza noticias **recientes** (fecha de publicación del artículo).
- Si hablan de un **libro recién publicado** o un evento editorial de las últimas semanas, sube el score.
- Piezas antiguas o evergreen sin gancho actual → score más bajo.

### Tier 1 de medios (cabeceras de referencia)
Los medios **Tier 1** tienen más peso editorial (revistas de ideas y prensa cultural de referencia):
- Tier 1 ideas: New Yorker, NYRB, Paris Review, LRB, Granta, Letras Libres, Merkur, etc.
- Tier 1 prensa: Guardian Books, NYT Books, Le Monde Livres, FAZ, NZZ, Die Zeit, Courrier International, Internazionale, El País Babelia, FT Books, The Economist Culture

Un artículo Tier 1 bien argumentado suele merecer **4 o 5**. Tier 2 parte de **3** salvo excepción.

## Prioridad 2 — Tier 2

Prensa generalista (secciones cultura/libros), semanarios, industria editorial (Publishers Weekly, etc.).
Incluir cuando aporten dato nuevo, contexto de mercado o amplíen una tendencia detectada en Tier 1.

## Descartar (score 1-2)

- Farándula, relleno, autopromoción
- Duplicados sin ángulo nuevo
- Contenido sin relación clara con libros, cultura editorial o ideas

## Traducción

- Titular y resumen **siempre en castellano** (español de España)
- Tono informativo, claro, sin sensacionalismo

## Escala relevance_score

| Score | Significado |
|-------|-------------|
| 5 | Destacado: imprescindible (Tier 1 + tema fuerte, o convergencia multi-medio) |
| 4 | Relevante: merece lectura |
| 3 | Secundario: interesante pero no prioritario |
| 2 | Marginal |
| 1 | Ruido — no incluir en informe |
