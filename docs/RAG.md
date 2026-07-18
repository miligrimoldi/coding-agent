# Base RAG

## Fuentes

Documentación técnica curada a mano, en Markdown con frontmatter YAML, en
`knowledge_base/raw/`:

| Archivo | Ecosistema | Fuente original |
|---|---|---|
| `nestjs/validation.md` | nestjs | [docs.nestjs.com/techniques/validation](https://docs.nestjs.com/techniques/validation) |
| `prisma/filtering.md` | prisma | [prisma.io — filtering and sorting](https://www.prisma.io/docs/orm/prisma-client/queries/filtering-and-sorting) |
| `prisma/migrations.md` | prisma | [prisma.io — Prisma Migrate](https://www.prisma.io/docs/orm/prisma-migrate) |

Cada documento declara metadata en su frontmatter (`title`, `ecosystem`,
`source_type`, `source_url`), que se propaga a cada chunk como filtro y
como fuente citable. El `ecosystem` de cada documento coincide con los
ecosistemas que el Researcher sabe detectar (`nestjs`, `prisma`, `jest`),
así que agregar cobertura para `jest` (o un ecosistema nuevo) es tan simple
como sumar un `.md` con ese `ecosystem` en el frontmatter — no requiere
tocar código.

## Pipeline de ingesta (`rag/ingest.py`)

```
knowledge_base/raw/*.md
        │  DocumentLoader (rag/document_loader.py)
        │  parsea frontmatter YAML, arma SourceDocument por archivo
        ▼
        │  MarkdownChunker (rag/chunker.py)
        │  parte por sección y por ventana deslizante de palabras
        ▼
        │  OpenAIEmbeddingProvider (rag/embeddings.py)
        │  embeddings por lote (text-embedding-3-small)
        ▼
        │  ChromaVectorStore (rag/vector_store.py)
        │  upsert en ChromaDB, persistido en disco
        ▼
knowledge_base/chroma/  (no versionado, se regenera con --reset)
```

Se corre con `python3 -m rag.ingest [--reset] [--batch-size N]`. Estado
actual: 3 documentos → **9 chunks**.

## Estrategia de chunking

`MarkdownChunker` (`rag/chunker.py`) combina dos niveles:

1. **División por sección**: detecta headings Markdown (`#` a `######`) con
   una regex por línea, y trata el contenido entre dos headings como una
   sección independiente (con "Introducción" para cualquier texto antes del
   primer heading). Esto mantiene la coherencia semántica del chunk — no
   corta a mitad de un tema.
2. **Ventana deslizante dentro de cada sección**: `chunk_size_words=180`
   palabras por chunk, con `overlap_words=30` palabras de solapamiento
   entre chunks consecutivos de la misma sección (para no perder contexto
   en el borde). Si una sección es más chica que el tamaño de chunk, queda
   como un único chunk.

Cada chunk final se arma como:

```
Título: <título del documento>
Sección: <heading de la sección>

<hasta 180 palabras de esa sección>
```

Incluir título y sección en el texto (no solo como metadata) ayuda a que el
embedding capture el contexto aunque el chunk se recupere aislado.

El `chunk_id` es determinístico: `sha256(source|section|chunk_index|text)`
truncado a 24 caracteres — permite volver a correr la ingesta sin duplicar
(`upsert`, no `insert`).

## Embeddings

`OpenAIEmbeddingProvider` (`rag/embeddings.py`) usa
`text-embedding-3-small` (configurable vía `EMBEDDING_MODEL`) sobre el
mismo cliente de OpenAI que usan los subagentes. Los embeddings se piden
por lote (`DEFAULT_BATCH_SIZE = 50` en `ingest.py`) para no mandar todos
los chunks en una sola request.

## Almacenamiento vectorial

**ChromaDB**, en modo `PersistentClient` sobre `knowledge_base/chroma/`
(gitignoreado — es un artefacto derivado, se regenera con la ingesta).
Espacio de similitud: coseno (`hnsw.space: cosine`). Cada chunk se guarda
con su embedding, el texto y su metadata completa (`source`, `title`,
`section`, `ecosystem`, `source_type`, `source_url`, `chunk_index`), lo que
permite filtrar la búsqueda por `ecosystem` sin tocar el índice.

## Recuperación (`rag/retriever.py` + `subagents/researcher.py`)

1. El Researcher detecta qué ecosistemas son relevantes para el pedido
   (`_detect_ecosystems`, cruzando el framework/dependencias que reportó el
   Explorer con keywords del pedido — por ejemplo, "prisma" solo se activa
   si el proyecto usa Prisma **y** el pedido menciona algo relacionado a
   persistencia/schema/filtro/migración, no en cualquier pedido).
2. Busca en el RAG **una vez por ecosistema detectado** (o una búsqueda
   global si no detectó ninguno), vía la tool `rag_search`.
3. Los resultados de todas las búsquedas se deduplican por `chunk_id`
   (quedándose con la de mayor similitud si el mismo chunk aparece en más
   de una búsqueda) y se ordenan por similitud descendente.
4. `Retriever.search` marca `evidence_sufficient` según un umbral configurable
   (`RAG_MIN_SIMILARITY`, default 0.45) sobre el resultado de mayor
   similitud. Si no hay evidencia suficiente, el Researcher recién ahí
   dispara el **fallback a búsqueda web** (Tavily), restringido a los
   dominios oficiales del ecosistema detectado
   (`docs.nestjs.com`, `prisma.io`, `jestjs.io`) — con una revalidación
   extra del lado del agente (`_is_allowed_url`) para no confiar
   ciegamente en que la API respete el filtro de dominio.

## Trazabilidad de fuentes

Cada `SubagentResult` del Researcher expone `rag_sources` (chunk_id,
source, title, section, source_url, similarity) y `web_sources` por
separado, y el campo `sources` del resultado distingue explícitamente
`repository | rag | web` según qué se haya usado — así el resto del
pipeline (y quien lea el `TaskState` final) puede diferenciar qué
información vino del repo, cuál del RAG, y cuál de una búsqueda web,
sin mezclarlas.
