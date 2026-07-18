# Coding Agent

Sistema multiagente de desarrollo de código, construido sin frameworks de
orquestación (LangChain, LangGraph, CrewAI, AutoGen, etc.). Un agente
principal (`Orchestrator`) coordina cinco subagentes especializados —
Explorer, Researcher, Implementer, Tester y Reviewer— para resolver pedidos
sobre un repositorio real, combinando herramientas locales, RAG sobre
documentación técnica, memoria persistente por proyecto, políticas de
seguridad configurables y observabilidad con Langfuse.

Caso de uso: un backend NestJS + Prisma (`target-project/issue-tracker-api`,
una API de tickets) sobre el que el agente agrega funcionalidad real,
corriendo build/lint/tests contra el proyecto de verdad.

## Más documentación

- [`docs/ARQUITECTURA.md`](docs/ARQUITECTURA.md) — rol del agente
  principal, de cada subagente, y estructura del estado compartido.
- [`docs/CASO_DE_USO.md`](docs/CASO_DE_USO.md) — ecosistema elegido,
  repositorio objetivo, objetivo concreto y criterio de éxito.
- [`docs/RAG.md`](docs/RAG.md) — fuentes, estrategia de chunking,
  embeddings y almacenamiento vectorial.
- [`docs/EVIDENCIA.md`](docs/EVIDENCIA.md) — tareas reales ejecutadas, con
  output, fuentes recuperadas y qué se observa en cada caso.
- [`docs/REFLEXION.md`](docs/REFLEXION.md) — qué funcionó, qué falló y qué
  mejoraríamos.

## Requisitos

- **Python 3.10+** (Langfuse 4.x no soporta Python 3.9).
- **Node.js reciente** y **npm** (para poder correr `npm install`/`build`/
  `test`/`lint` sobre el proyecto objetivo; `package.json` no fija un
  mínimo explícito, se desarrolló y probó con Node v26).
- Una API key de OpenAI.
- Opcional: API key de [Tavily](https://tavily.com) (fallback de búsqueda
  web) y credenciales de [Langfuse](https://langfuse.com) (observabilidad).

## Instalación

```bash
# 1. Crear y activar un entorno virtual
python3 -m venv .venv
source .venv/bin/activate   # en Windows: .venv\Scripts\activate

# 2. Instalar dependencias de Python
pip install -r requirements.txt

# 3. Instalar dependencias del proyecto objetivo
cd target-project/issue-tracker-api
npm install
npx prisma generate
cd ../..
```

## Configuración

### Variables de entorno

Copiá `.env.example` a `.env` y completá lo que necesites:

```bash
cp .env.example .env
```

| Variable | Obligatoria | Para qué |
|---|---|---|
| `OPENAI_API_KEY` | Sí | LLM (subagentes) y embeddings (RAG) |
| `EMBEDDING_MODEL`, `RAG_COLLECTION`, `RAG_TOP_K`, `RAG_MIN_SIMILARITY` | No | Tuning del RAG (tienen default) |
| `TAVILY_API_KEY` | No | Fallback de búsqueda web del Researcher cuando el RAG no alcanza. Sin esto, el fallback web simplemente no aporta resultados |
| `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_BASE_URL` | No | Observabilidad. Sin estas keys, `observability.py` corre en modo no-op (el agente funciona igual, pero no se registra ninguna traza) |

El proyecto objetivo (`target-project/issue-tracker-api`) necesita su
**propio** `.env` con `DATABASE_URL="file:./dev.db"` (no se versiona, está en
su `.gitignore`).

### `agent.config.yaml`

Define las políticas de seguridad que se validan antes de cada tool call:
workspace permitido, paths de lectura/escritura prohibidos (`.env`,
`secrets/**`, `**/*.pem`, lockfiles, `.github/**`), comandos prohibidos
(`rm -rf`, `git push`, `sudo`, etc.) y comandos/categorías que requieren
aprobación manual por consola (`npm install`, `git commit`, cualquier
`write_file`). Ver `policy_engine.py` para el detalle de cómo se aplican.

### Base RAG

La base vectorial (ChromaDB) no se versiona (`knowledge_base/chroma/` está
gitignoreado). Hay que generarla una vez, a partir de los documentos en
`knowledge_base/raw/`:

```bash
python3 -m rag.ingest --reset
```

Correlo de nuevo (sin `--reset` para agregar, con `--reset` para reindexar
desde cero) cada vez que agregues o modifiques documentos en
`knowledge_base/raw/`.

## Ejecución

```bash
python3 main.py [workspace] ["pedido en lenguaje natural"]
```

Ambos argumentos son opcionales — por default usa
`./target-project/issue-tracker-api` como workspace y un pedido genérico de
prueba. El `workspace` pasado tiene que coincidir con el `workspace`
configurado en `agent.config.yaml`, o el agente corta de entrada sin gastar
ninguna llamada al modelo.

Ejemplos:

```bash
python3 main.py ./target-project/issue-tracker-api \
  "Agregar un endpoint GET /tickets/:id que devuelva un ticket por id, con 404 si no existe."

python3 main.py ./target-project/issue-tracker-api \
  "Explicame cómo está implementada la creación de tickets."

python3 main.py ./target-project/issue-tracker-api \
  "Analizar el proyecto y señalar riesgos, sin modificar archivos."
```

El agente detecta automáticamente el tipo de pedido (implementación,
análisis de solo lectura, o descripción) y ajusta qué subagentes corre.
Durante la ejecución, cualquier operación de escritura va a pedir
aprobación por consola (`¿Aprobar? (yes/no)`).

La salida es el `TaskState` final en JSON, con el estado (`done` / `blocked`
/ `needs_help`), el log de progreso, los resultados de cada subagente, las
fuentes consultadas y los archivos modificados.

## Tests

```bash
python3 -m pytest tests/ -v
```

Son tests aislados con subagentes/dependencias falsas — no llaman al LLM ni
gastan tokens.

## Memoria persistente

Cada corrida actualiza `memory/<proyecto>-<hash>.json` con arquitectura
detectada, archivos importantes, dependencias, comandos que funcionaron,
decisiones tomadas y bugs investigados sobre ese workspace puntual. Esos
archivos no se versionan (son estado local, se regeneran solos).

## Observabilidad

Con las credenciales de Langfuse configuradas en `.env`, cada corrida queda
registrada como una traza completa: llamadas al LLM (prompts, modelo,
tokens, costo estimado, latencia), cada tool call, documentos recuperados
del RAG, búsquedas web e iteraciones por subagente. Sin credenciales, el
agente funciona exactamente igual pero no se registra nada.

## Estructura del repo

```
main.py                  Punto de entrada
orchestrator.py          Agente principal: coordina el pipeline
policy_engine.py         Valida cada tool call contra agent.config.yaml
tool_executor.py         Ejecuta tools ya validadas, registra efectos y trazas
task_state.py            Estado compartido de una tarea
project_memory.py        Memoria persistente entre corridas, por proyecto
request_mode.py          Clasifica el pedido (implementación/análisis/descripción)
observability.py         Integración con Langfuse
subagents/               Explorer, Researcher, Implementer, Tester, Reviewer
tools/                   Sistema de plugins de tools (loader + plugins/)
rag/                     Chunking, embeddings, vector store, retriever, ingesta
knowledge_base/raw/      Documentos fuente del RAG (versionados)
target-project/          El repo objetivo sobre el que trabaja el agente
tests/                   Tests unitarios del harness (sin LLM)
evidence/                Evidencia de corridas reales
```
