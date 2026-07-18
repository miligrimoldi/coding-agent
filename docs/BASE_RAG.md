# Base RAG

## Objetivo

La base RAG proporciona al subagente Researcher documentación técnica
recuperable y citable sobre los ecosistemas utilizados por el repositorio
objetivo.

Su propósito es reducir la dependencia del conocimiento general del modelo y
hacer que las recomendaciones técnicas se apoyen en fuentes identificables.

La estrategia general es:

```text
Pedido del usuario
        ↓
Evidencia del repositorio reunida por Explorer
        ↓
Consulta a la base RAG local
        ↓
Evaluación numérica y semántica de la evidencia
        ↓
Fallback web oficial solamente cuando hace falta
```

El Researcher nunca debería usar la web como primera opción. Primero consulta
la base local y conserva por separado la evidencia proveniente del repositorio,
del RAG, de la web y de inferencias.

## Fuentes utilizadas

La documentación se encuentra en:

```text
knowledge_base/raw/
```

Los documentos fueron curados manualmente y almacenados como Markdown con
frontmatter YAML.

| Archivo | Ecosistema | Fuente original |
|---|---|---|
| `nestjs/validation.md` | `nestjs` | [NestJS: Validation](https://docs.nestjs.com/techniques/validation) |
| `prisma/filtering.md` | `prisma` | [Prisma: Filtering and sorting](https://www.prisma.io/docs/orm/prisma-client/queries/filtering-and-sorting) |
| `prisma/migrations.md` | `prisma` | [Prisma Migrate](https://www.prisma.io/docs/orm/prisma-migrate) |
| `jest/testing-and-linting.md` | `jest` | Guía interna curada: `internal://jest/testing-and-linting` |

La base actual contiene **4 documentos y 15 chunks**.

La documentación local de Jest fue agregada después de las primeras pruebas del
pipeline. Esas ejecuciones mostraron que, aunque el agente podía generar tests
funcionales, todavía necesitaba evidencia más específica para evitar casts
inseguros como `as any`, conservar los tests existentes y producir archivos
compatibles con ESLint y Prettier.

## Formato de los documentos

Cada documento puede comenzar con frontmatter YAML:

```yaml
---
title: NestJS - Validación de DTOs
ecosystem: nestjs
source_type: official_documentation
source_url: https://docs.nestjs.com/techniques/validation
---
```

El `DocumentLoader` conserva los siguientes datos:

- `source`: path relativo dentro de `knowledge_base/raw/`;
- `title`;
- `content`;
- `ecosystem`;
- `source_type`;
- `source_url`;
- metadata adicional del frontmatter.

Las extensiones admitidas son:

```text
.md
.txt
```

Cuando no se declara `ecosystem`, se utiliza como fallback el nombre de la
carpeta padre. El valor se normaliza a minúsculas.

Agregar documentación de Jest u otro ecosistema requiere incorporar un nuevo
documento con el frontmatter correspondiente y volver a ejecutar la ingesta;
no es necesario modificar el código del chunker ni del vector store.

## Pipeline de ingesta

La ingesta se implementa en `rag/ingest.py`:

```text
knowledge_base/raw/
        │
        │ DocumentLoader
        │ Lee Markdown/TXT y parsea el frontmatter YAML
        ▼
SourceDocument[]
        │
        │ MarkdownChunker
        │ Divide por secciones y ventanas de palabras
        ▼
DocumentChunk[]
        │
        │ OpenAIEmbeddingProvider
        │ Genera embeddings por lotes
        ▼
Embeddings
        │
        │ ChromaVectorStore.upsert
        ▼
knowledge_base/chroma/
```

La ingesta se ejecuta desde la raíz del proyecto:

```bash
python -m rag.ingest --reset
```

También puede configurarse el tamaño de lote:

```bash
python -m rag.ingest --reset --batch-size 50
```

`--reset` elimina la colección anterior y la vuelve a crear antes de insertar
los chunks actuales.

La ingesta devuelve un resumen como:

```json
{
  "documents_loaded": 4,
  "chunks_generated": 15,
  "chunks_processed": 15,
  "collection_count": 15,
  "sources": []
}
```

## Estrategia de chunking

El componente `MarkdownChunker`, ubicado en `rag/chunker.py`, utiliza dos
niveles de segmentación.

### 1. División por secciones Markdown

Una expresión regular detecta encabezados de nivel 1 a 6:

```text
# Título
## Sección
### Subsección
```

El contenido comprendido entre dos encabezados se trata como una sección
independiente.

Casos especiales:

- el texto anterior al primer encabezado se almacena como `Introducción`;
- un documento sin encabezados se procesa como una única sección llamada
  `Documento`;
- las secciones vacías se ignoran.

Esta división ayuda a evitar que un chunk mezcle temas técnicos diferentes.

### 2. Ventana deslizante por palabras

Dentro de cada sección se utiliza:

```text
chunk_size_words = 180
overlap_words = 30
step = 150 palabras
```

El solapamiento conserva parte del contexto cuando una explicación queda
dividida entre dos chunks consecutivos.

Una sección de menos de 180 palabras produce un único chunk.

### Texto final del chunk

Cada chunk incorpora el título y la sección dentro del texto que se envía al
modelo de embeddings:

```text
Título: <título del documento>
Sección: <nombre de la sección>

<contenido del fragmento>
```

El título y la sección también se guardan como metadata. Incluirlos en el texto
mejora el contexto semántico cuando el fragmento se recupera de forma aislada.

### Identificadores determinísticos

El `chunk_id` se calcula mediante:

```text
sha256(source | section | chunk_index | text)
```

y se trunca a 24 caracteres.

Esto permite ejecutar la ingesta varias veces sin duplicar documentos, ya que
ChromaDB utiliza `upsert` en lugar de `insert`.

## Embeddings

Los embeddings se generan con `OpenAIEmbeddingProvider`, definido en
`rag/embeddings.py`.

El modelo predeterminado es:

```text
text-embedding-3-small
```

y puede configurarse mediante:

```env
EMBEDDING_MODEL=text-embedding-3-small
```

El mismo proveedor se utiliza para:

- generar los embeddings de los chunks durante la ingesta;
- generar el embedding de cada consulta durante la recuperación.

Esto mantiene documentos y consultas dentro del mismo espacio vectorial.

Los chunks se procesan por lotes. El valor predeterminado es:

```text
DEFAULT_BATCH_SIZE = 50
```

La respuesta de OpenAI se ordena por el índice de cada embedding antes de
devolver la lista, preservando la correspondencia con los chunks originales.

Las llamadas de embeddings también quedan registradas en Langfuse, junto con el
modelo, tokens, costo y latencia.

## Almacenamiento vectorial

Se utiliza **ChromaDB** en modo persistente:

```python
chromadb.PersistentClient(
    path="knowledge_base/chroma"
)
```

El directorio es:

```text
knowledge_base/chroma/
```

y se encuentra ignorado por Git porque es un artefacto derivado que puede
regenerarse desde `knowledge_base/raw/`.

La colección predeterminada se llama:

```text
technical_docs
```

y puede modificarse mediante:

```env
RAG_COLLECTION=technical_docs
```

La colección usa un índice HNSW con distancia coseno:

```python
configuration={
    "hnsw": {
        "space": "cosine"
    }
}
```

Por cada chunk se almacena:

- ID determinístico;
- texto;
- embedding;
- `source`;
- `title`;
- `section`;
- `ecosystem`;
- `source_type`;
- `source_url`;
- `chunk_index`.

Ejemplo de metadata:

```json
{
  "source": "nestjs/validation.md",
  "title": "NestJS - Validación de DTOs",
  "section": "ValidationPipe",
  "ecosystem": "nestjs",
  "source_type": "official_documentation",
  "source_url": "https://docs.nestjs.com/techniques/validation",
  "chunk_index": 0
}
```

La metadata permite filtrar por ecosistema sin crear una colección diferente
para cada tecnología.

## Estrategia de recuperación

La recuperación se implementa mediante:

```text
rag/retriever.py
subagents/researcher.py
tools/plugins/rag_search.py
```

### Detección de ecosistemas

El Researcher detecta los ecosistemas relevantes cruzando:

- framework informado por el Explorer;
- dependencias encontradas;
- paths relevantes;
- palabras clave del pedido.

Por ejemplo:

- NestJS se activa cuando el framework o las dependencias contienen Nest;
- Prisma se activa cuando el repositorio usa Prisma y el pedido se relaciona
  con persistencia, schema, filtros, migraciones o eliminación;
- Jest se activa cuando el proyecto utiliza Jest y el pedido menciona tests,
  pruebas, specs o e2e;
- además, la presencia de archivos relevantes con `.spec.` o `.test.` permite
  detectar Jest incluso cuando el Explorer no logró completar correctamente la
  lista de dependencias.

Esta última regla fue agregada después de observar que algunas exploraciones
identificaban el archivo de test pero devolvían una lista de dependencias vacía.
Con esta mejora, el Researcher puede seguir recuperando la guía local de testing
y linting a partir de la evidencia estructural del repositorio.

Esto evita consultar documentación de Prisma o Jest en tareas que no la
necesitan y, al mismo tiempo, reduce falsos negativos en tareas claramente
orientadas a pruebas.

### Consulta por ecosistema

El Researcher ejecuta una búsqueda RAG por cada ecosistema detectado.

Aunque el Retriever tiene un valor general configurable:

```env
RAG_TOP_K=5
```

el Researcher solicita actualmente hasta **4 resultados por ecosistema** para
mantener acotado el contexto enviado al modelo.

Si no se detecta ningún ecosistema, se realiza una búsqueda global.

### Similitud

ChromaDB devuelve distancia coseno. El sistema la transforma en similitud:

```text
similarity = 1 - distance
```

El umbral predeterminado es:

```env
RAG_MIN_SIMILARITY=0.45
```

`Retriever.search()` devuelve:

```json
{
  "query": "...",
  "ecosystem_filter": "nestjs",
  "results": [],
  "result_count": 0,
  "top_similarity": null,
  "minimum_similarity": 0.45,
  "evidence_sufficient": false
}
```

Cada resultado contiene:

- `chunk_id`;
- texto;
- metadata;
- distancia;
- similitud.

### Combinación y deduplicación

Los resultados de las consultas por ecosistema se combinan y se deduplican por
`chunk_id`.

Si un mismo chunk aparece más de una vez, se conserva la versión con mayor
similitud. Finalmente, los resultados se ordenan en forma descendente.

## Evaluación de suficiencia y fallback web

La suficiencia se evalúa en dos niveles:

1. **Evaluación numérica:** el Retriever compara la mayor similitud con
   `RAG_MIN_SIMILARITY`.
2. **Evaluación semántica:** el Researcher analiza si los chunks realmente
   cubren el tema técnico central del pedido.

Después de la primera síntesis, el fallback web se activa cuando:

- el Researcher devuelve `needs_web_fallback: true`; o
- la evidencia total se considera insuficiente.

La búsqueda web se implementa con Tavily y queda restringida a dominios
oficiales:

```text
NestJS → docs.nestjs.com
Prisma → prisma.io
Jest   → jestjs.io
```

La tool vuelve a comprobar el hostname de cada URL con `_is_allowed_url` antes
de conservar el resultado. De esta forma, el agente no confía únicamente en
que la API externa respete el filtro solicitado.

El flujo es siempre:

```text
Repositorio
    ↓
RAG
    ↓
Evaluación de suficiencia
    ↓
Web oficial, solo cuando corresponde
```

## Trazabilidad de fuentes

El resultado del Researcher mantiene las fuentes separadas.

### Fuentes RAG

`rag_sources` contiene:

```json
{
  "chunk_id": "...",
  "source": "nestjs/validation.md",
  "title": "NestJS - Validación de DTOs",
  "section": "ValidationPipe",
  "source_url": "https://docs.nestjs.com/techniques/validation",
  "similarity": 0.61
}
```

### Fuentes web

`web_sources` conserva, según la respuesta disponible:

- título;
- URL;
- fragmento de contenido;
- score;
- tiempo de respuesta.

### Procedencia general

El campo `sources` de cada `SubagentResult` diferencia explícitamente:

```text
repository
memory
rag
web
```

Así, los siguientes subagentes y quien inspecciona el `TaskState` pueden saber
qué parte de la evidencia provino del código, de memoria persistente, de la
base local o de una búsqueda externa.

Las tools `rag_search` y `web_search`, los documentos recuperados, sus
similitudes y las fuentes también quedan registrados en Langfuse.

## Reproducibilidad y actualización

La base vectorial no se versiona, pero se puede reconstruir completamente a
partir de los documentos fuente:

```bash
python -m rag.ingest --reset
```

Para agregar cobertura documental:

1. crear un archivo `.md` o `.txt` dentro de `knowledge_base/raw/`;
2. agregar frontmatter con título, ecosistema, tipo y URL;
3. ejecutar nuevamente la ingesta;
4. comprobar el número de documentos, chunks y registros de la colección.

Esta estrategia mantiene versionadas las fuentes humanas y evita incluir en el
repositorio binarios o índices derivados.