# Arquitectura

## Vista general

Un agente principal (`Orchestrator`) coordina una secuencia fija de
subagentes especializados, cada uno con su propio set acotado de tools y su
propia responsabilidad. No hay ningún framework de orquestación de por
medio: el flujo de control es código Python directo (`orchestrator.py`), y
cada subagente maneja su propio loop de function-calling contra la API de
OpenAI.

```
                         ┌──────────────┐
 pedido del usuario ───► │ Orchestrator │ ───► TaskState final (JSON)
                         └──────┬───────┘
                                │ decide el modo del pedido
                                │ (request_mode.py)
                                ▼
        ┌───────────┬──────────────┬─────────────┬──────────┐
        │  Explorer │  Researcher  │ Implementer │  Tester  │──► Reviewer
        └───────────┴──────────────┴─────────────┴──────────┘
              todos comparten el mismo TaskState
```

## El agente principal: `Orchestrator`

Vive en `orchestrator.py`. Sus responsabilidades:

1. **Recibe el pedido** y crea el `TaskState` inicial.
2. **Clasifica el pedido** con `request_mode.py` en tres modos:
   - `DESCRIPTION` — el usuario solo quiere una explicación. Corre únicamente
     el Explorer y termina.
   - `ANALYSIS` — el usuario pide un análisis o auditoría sin tocar código.
     Corre Explorer + Researcher y termina, sin pasar por Implementer.
   - `IMPLEMENTATION` (default) — el pipeline completo.
3. **Coordina la secuencia** de subagentes (`call_subagent`), registrando
   cada resultado en el `TaskState` compartido.
4. **Corre el ciclo Implementer ↔ Tester** con reintentos acotados
   (`MAX_IMPLEMENT_ATTEMPTS = 3`): si el Tester falla, el Implementer vuelve
   a ser llamado con el resultado del fallo como contexto para corregir.
5. **Detecta loops y evidencia insuficiente** (ver más abajo) y decide
   cuándo cortar en vez de seguir reintentando a ciegas.
6. **Persiste la memoria del proyecto** al final de cada corrida, pase lo
   que pase (`_save_memory`, con manejo de errores propio para que un fallo
   al guardar no tire abajo el resultado real de la tarea).
7. **Envuelve toda la ejecución en observabilidad** (Langfuse): un trace raíz
   por corrida, con un span por subagente y, dentro de cada uno, un span por
   tool call.

El Orchestrator **no ejecuta tools directamente** — delega toda tool
execution en `ToolExecutor`, que a su vez consulta a `PolicyEngine` antes de
correr nada.

## Los subagentes

Cada subagente implementa `run(task_state) -> SubagentResult`
(`subagents/subagent_protocol.py` define el protocolo). No todos tienen
acceso a las mismas tools:

| Subagente | Tools permitidas | Responsabilidad |
|---|---|---|
| **Explorer** | `read_file`, `list_files` | Entender el repositorio: lenguaje, framework, dependencias, estructura, archivos relevantes para el pedido. Solo lectura. |
| **Researcher** | `read_file`, `rag_search`, `web_search` | Investigar cómo resolver el pedido técnicamente: verifica puntualmente archivos que el Explorer marcó como relevantes, busca en el RAG por ecosistema (NestJS/Prisma/Jest), y recién si el RAG no alcanza, hace fallback a búsqueda web restringida a dominios oficiales. |
| **Implementer** | `read_file`, `write_file`, `list_files`, `run_command` | Aplica los cambios de código reales. `run_command` es para casos puntuales (ej. `npx prisma generate`), no para correr los checks generales — eso es trabajo del Tester. |
| **Tester** | `run_command` | Corre las validaciones reales del proyecto: build, lint, tests (comandos resueltos dinámicamente, ver abajo). |
| **Reviewer** | `read_file`, `list_files` | Revisa los archivos efectivamente modificados contra el pedido original y el resultado del Tester, y aprueba o rechaza. Solo lectura. |

### Explorer, Implementer, Reviewer: loop de function-calling con salvaguardas

Estos tres subagentes comparten un patrón: un loop de hasta N iteraciones
llamando al LLM con `tools=<sus tools>`, donde en cada iteración el modelo
puede pedir una tool call o devolver su respuesta final en JSON. Salvaguardas
comunes:

- **Detección de repetición** (`task_state.is_repeating`): si la misma tool
  se llama con los mismos argumentos una segunda vez, se bloquea la tercera
  y se le avisa al modelo que cambie de estrategia.
- **Última iteración forzada**: en la iteración final, se llama al modelo con
  `tool_choice="none"` (no puede pedir más tools) y se le repite el schema
  JSON exacto esperado, para garantizar que siempre devuelva algo parseable
  en vez de cortar en seco sin respuesta.
- **Verificación anti-alucinación**: Explorer e Implementer no confían en lo
  que el modelo *dice* haber leído/escrito — reconstruyen esa información a
  partir de las tool calls realmente ejecutadas (`read_files_this_run`,
  `written_files_this_run`) y descartan cualquier afirmación sin evidencia
  real detrás.
- El Implementer además fuerza la acción: si el modelo lee de más sin
  escribir nada, o si el pedido exige tests y todavía no se tocó ningún
  archivo de test, se lo empuja con `tool_choice` forzado a `write_file` en
  vez de dejar que seleccione otra tool que retrase el compromiso.

### Tester: comandos resueltos dinámicamente

El Tester no tiene una lista fija de comandos. Los resuelve por prioridad:

1. Override manual (si se instancia con `test_commands` explícito).
2. **Memoria del proyecto** (`useful_commands`): comandos ya validados en
   corridas anteriores sobre este mismo workspace.
3. **`scripts_detectados` del Explorer** (de esta misma corrida): construye
   `npm run <script>` para lint/build/test, y antepone
   `npx prisma validate` si detecta evidencia de Prisma.
4. Comandos por default, si no hay evidencia de ningún lado.

Memoria y Explorer se **combinan por clave**, no son alternativas
excluyentes: si `lint` nunca pasó (no está en memoria todavía), se sigue
pidiendo al Explorer aunque `build`/`test` ya estén validados en memoria —
evita que un check roto desaparezca silenciosamente del set solo porque
otros ya se confirmaron.

## Estado compartido: `TaskState`

Vive en `task_state.py`, se instancia una vez por corrida y todos los
subagentes lo leen/escriben. Campos principales:

- `original_request` — el pedido original, sin modificar.
- `status` — `in_progress` | `done` | `blocked` | `needs_help`.
- `progress_log` — historial legible con timestamp de cada paso.
- `subagent_results` — lista de `SubagentResult` por subagente (puede haber
  más de uno si el Implementer se reintentó).
- `sources_consulted` — acumulado de `repository | memory | rag | web`, para
  poder diferenciar de dónde salió cada pieza de información.
- `files_modified` — lista real de archivos tocados. Se llena automáticamente
  desde `ToolExecutor` (no desde lo que el subagente declara): tanto cuando
  se llama `write_file`, como cuando un comando tiene efectos secundarios en
  el workspace (ej. un lint con `--fix`, detectado vía `git status`).
- `observations` — notas libres (errores, bloqueos de política, avisos de
  repetición).
- `tool_call_history` — cada tool call, con argumentos, resultado y
  duración; es la base tanto para `is_repeating` como para la auditoría.
- `project_memory` — referencia al `ProjectMemory` de este workspace
  (ver más abajo).

## Memoria persistente (`project_memory.py`)

A diferencia de `TaskState` (vive y muere con una tarea), `ProjectMemory`
sobrevive entre corridas: un JSON por workspace en `memory/`, con
arquitectura detectada, archivos importantes, dependencias, comandos
validados, decisiones tomadas y bugs investigados (resueltos o no). Se
actualiza incrementalmente durante la corrida (el Explorer la enriquece, el
Tester valida comandos contra ella, el ciclo de reintento registra bugs) y
se persiste siempre al final, incluso si la tarea terminó bloqueada.

## Políticas y ejecución de tools

`PolicyEngine` (`policy_engine.py`) valida **cada** tool call contra
`agent.config.yaml` antes de que se ejecute: workspace permitido, patrones
de paths denegados para lectura/escritura (con semántica tipo `.gitignore`
— bloquean en cualquier profundidad del árbol, no solo en la raíz),
comandos prohibidos y comandos/categorías que requieren aprobación humana
por consola.

`ToolExecutor` (`tool_executor.py`) es el único punto que efectivamente
ejecuta una tool: aplica los permisos propios del subagente (su
`ALLOWED_TOOLS`), pide la validación a `PolicyEngine`, gestiona la
aprobación humana cuando corresponde, ejecuta la tool, registra el efecto
sobre `TaskState`, y envuelve todo en un span de observabilidad.

## Comportamiento seguro: loops y evidencia insuficiente

- **Repetición dentro de un subagente**: `is_repeating` corta la misma tool
  call repetida (ver arriba).
- **Loop en el ciclo Implementer↔Tester**: si dos intentos consecutivos
  fallan con el *mismo* error (mismo comando, mismo tipo de fallo —
  comparado con un fingerprint que ignora ruido como duraciones o números de
  línea), el ciclo se corta antes de agotar los reintentos y la tarea queda
  en `needs_help`, con una observación explicando qué comando sigue
  fallando. En este caso el Reviewer **no** llega a correr — el corte pasa
  directamente al resultado final.
- **El Implementer declina actuar**: si no hay evidencia suficiente o el
  pedido choca con una restricción explícita, el Implementer no escribe
  nada y lo marca (`evidence_sufficient: false`). El Orchestrator reconoce
  esto como `needs_help` de inmediato (sin llamar a Tester ni a Reviewer),
  no como un éxito trivial.
- **Requisitos ambiguos**: si el Researcher determina que el pedido no tiene
  información suficiente para avanzar con confianza
  (`requirements_clear=False`), el Orchestrator corta antes de llegar al
  Implementer y junta las aclaraciones necesarias en una observación.
- **Workspace mal configurado**: si el workspace pasado no coincide con el
  de `agent.config.yaml`, se corta en el primer chequeo, antes de gastar
  ninguna llamada al modelo (evita quemar todo el pipeline sabiendo de
  antemano que cada tool call va a fallar).
