# Arquitectura

## Vista general

El sistema está compuesto por un agente principal, denominado
`Orchestrator`, que coordina un pipeline de subagentes especializados según
el tipo de pedido recibido.

Cada subagente tiene:

- una responsabilidad específica;
- un conjunto acotado de tools;
- acceso al mismo `TaskState`;
- límites de iteración y mecanismos de seguridad;
- un resultado estructurado mediante `SubagentResult`.

No se utiliza ningún framework de orquestación. El flujo de control está
implementado directamente en Python, principalmente en `orchestrator.py`.

```text
                           ┌──────────────┐
pedido del usuario ──────► │ Orchestrator │
                           └──────┬───────┘
                                  │
                                  ▼
                         detect_request_mode
                                  │
             ┌────────────────────┼─────────────────────┐
             │                    │                     │
             ▼                    ▼                     ▼
       DESCRIPTION             ANALYSIS          IMPLEMENTATION
             │                    │                     │
         Explorer        Explorer → Researcher   Explorer → Researcher
             │                    │                     │
            done                 done             Implementer ↔ Tester
                                                        │
                                                     Reviewer
                                                        │
                                                       done
```

El pipeline no es siempre idéntico. El Orchestrator adapta la secuencia según
la intención del usuario:

- una descripción puede terminar después del Explorer;
- un análisis puede terminar después del Researcher;
- una implementación utiliza el pipeline completo.

## Agente principal: `Orchestrator`

El agente principal vive en:

```text
orchestrator.py
```

Sus responsabilidades principales son:

1. recibir el pedido del usuario;
2. resolver y validar el workspace;
3. crear el `TaskState` inicial;
4. cargar la memoria persistente del proyecto;
5. clasificar el pedido;
6. decidir qué subagentes ejecutar;
7. coordinar los resultados;
8. gestionar reintentos entre Implementer y Tester;
9. detectar evidencia insuficiente o loops sin progreso;
10. definir el estado final;
11. persistir la memoria;
12. registrar la ejecución en Langfuse.

El Orchestrator no ejecuta tools directamente. Toda ejecución pasa por
`ToolExecutor`, que consulta a `PolicyEngine` antes de realizar cualquier
acción.

## Clasificación del pedido

La clasificación se implementa en:

```text
request_mode.py
```

El sistema distingue tres modos.

### `DESCRIPTION`

Se utiliza cuando el usuario solicita una explicación sobre el repositorio o
su implementación actual.

Flujo:

```text
Explorer → done
```

Características:

- solo lectura;
- no se invoca Researcher;
- no se invoca Implementer;
- no se ejecutan tests;
- no se modifican archivos.

### `ANALYSIS`

Se utiliza cuando el usuario pide analizar, auditar, comparar o recomendar
mejoras sin modificar el proyecto.

Flujo:

```text
Explorer → Researcher → done
```

Características:

- inspección selectiva del repositorio;
- consulta RAG;
- posible fallback web;
- recomendaciones técnicas;
- ausencia de escrituras.

### `IMPLEMENTATION`

Es el modo predeterminado para pedidos que requieren modificar el
repositorio.

Flujo:

```text
Explorer
    ↓
Researcher
    ↓
Implementer
    ↓
Tester
    ↓
Reviewer
```

Cuando el Tester falla, el Orchestrator puede volver a llamar al Implementer
con el feedback del intento anterior:

```text
Implementer → Tester → Implementer → Tester
```

El máximo actual es:

```text
MAX_IMPLEMENT_ATTEMPTS = 3
```

## Protocolo común de subagentes

El protocolo está definido en:

```text
subagents/subagent_protocol.py
```

Cada subagente implementa:

```python
run(task_state: TaskState) -> SubagentResult
```

El resultado conserva:

- nombre del subagente;
- resumen;
- datos estructurados;
- fuentes consultadas;
- timestamp.

Esto permite que los siguientes subagentes trabajen con una síntesis
estructurada, en lugar de depender de todo el historial textual anterior.

## Subagentes

### Explorer

Tools permitidas:

```text
list_files
read_file
```

Responsabilidad:

- identificar lenguaje y framework;
- inspeccionar la estructura;
- detectar dependencias;
- localizar scripts;
- encontrar archivos relevantes;
- reconstruir el flujo actual;
- distinguir qué aspectos fueron verificados y cuáles no.

El Explorer es de solo lectura.

No debe inventar archivos ni contenido. Para reducir alucinaciones, la lista
final de archivos leídos se reconstruye a partir de las tool calls realmente
ejecutadas durante la corrida.

Su resultado puede incluir:

```text
task_mode
lenguaje
framework
resumen_para_usuario
archivos_leidos
archivos_relevantes
estructura
dependencias_detectadas
scripts_detectados
flujo_actual
configuraciones_verificadas
aspectos_no_verificados
puntos_de_entrada_sugeridos
```

### Researcher

Tools permitidas:

```text
read_file
rag_search
web_search
```

Responsabilidad:

- utilizar el contexto producido por Explorer;
- verificar puntualmente archivos relevantes;
- detectar ecosistemas técnicos;
- consultar la base RAG;
- evaluar la suficiencia de la evidencia;
- utilizar fallback web cuando corresponde;
- distinguir hechos, recomendaciones, riesgos e inferencias;
- determinar si los requisitos están suficientemente claros.

El orden esperado es:

```text
repositorio → RAG → evaluación → web
```

La web no se utiliza como primera opción.

El Researcher puede devolver:

```text
evidence_sufficient
requirements_clear
clarifications_needed
current_implementation
suggested_improvements
findings
rag_sources
web_sources
risks_or_unknowns
inferences
```

Cuando:

```text
requirements_clear = false
```

el Orchestrator termina la tarea en `needs_help` antes de invocar al
Implementer.

### Implementer

Tools permitidas:

```text
list_files
read_file
write_file
run_command
```

Responsabilidad:

- leer el código actual antes de modificarlo;
- aplicar únicamente cambios respaldados por evidencia;
- conservar comportamiento existente;
- modificar la menor cantidad posible de archivos;
- agregar tests cuando el pedido lo requiere;
- corregir los errores informados por el Tester;
- declarar riesgos o limitaciones.

Las escrituras requieren aprobación humana según la política configurada. El run command solo se usa para casos concretos
como cuando se tiene que generar un client de prisma. La idea es que la responsabilidad de ejecutar comandos sea del tester.

El Implementer valida sus resultados contra las tool calls realmente
ejecutadas. No confía únicamente en el texto producido por el modelo para
determinar qué archivos fueron escritos.

Si el modelo afirma que no existe evidencia suficiente y no modifica
archivos, el Orchestrator interpreta el resultado como `needs_help`, no como
una implementación exitosa.

### Tester

Tool permitida:

```text
run_command
```

Responsabilidad:

- resolver los comandos de validación;
- ejecutar checks reales;
- conservar stdout, stderr y código de salida;
- indicar qué validaciones pasaron;
- devolver todos los fallos al Implementer.

El Tester es principalmente determinístico. No implementa cambios de código.

Los comandos se resuelven por prioridad:

1. override manual;
2. memoria persistente del proyecto;
3. scripts detectados por Explorer;
4. defaults seguros.

Memoria y Explorer se combinan por clave. Por ejemplo, si la memoria conoce
`build` y `test`, pero todavía no tiene un comando de `lint` validado, el
Tester puede completar ese dato con lo detectado por Explorer.

Para el repositorio objetivo se ejecutan normalmente:

```text
npx prisma validate
npm run lint
npm run build
npm run test
```

Un check fallido impide aprobar la tarea, aunque los demás hayan pasado.

### Reviewer

Tools permitidas:

```text
list_files
read_file
```

Responsabilidad:

- revisar los archivos registrados como modificados;
- comparar el resultado contra el pedido original;
- verificar el resultado final del Tester;
- confirmar que no faltan partes del pedido;
- detectar cambios innecesarios;
- señalar inconsistencias entre archivos declarados y detectados;
- aprobar o rechazar.

El Reviewer no se limita a comprobar que los tests pasaron.

Debe responder conceptualmente preguntas como:

- ¿se implementó exactamente lo pedido?
- ¿se conservaron las restricciones originales?
- ¿se agregaron los tests solicitados?
- ¿se modificaron archivos ajenos al pedido?
- ¿los cambios declarados coinciden con los archivos detectados?

## Loops de function-calling

Explorer, Implementer y Reviewer utilizan loops acotados de
function-calling.

En cada iteración el modelo puede:

- solicitar una tool;
- continuar inspeccionando;
- devolver un resultado final estructurado.

El número máximo de iteraciones depende del subagente.

### Detección de repetición

`TaskState.is_repeating()` permite detectar una misma tool call con los mismos
argumentos.

Cuando se supera el umbral, el sistema bloquea la repetición y le indica al
modelo que debe cambiar de estrategia.

Esto evita loops como:

```text
read_file(A)
read_file(A)
read_file(A)
read_file(A)
```

### Última iteración sin tools

En la última iteración se utiliza:

```text
tool_choice = none
```

y se vuelve a indicar el schema esperado.

Esto aumenta la probabilidad de obtener una respuesta final estructurada.

No se considera una garantía absoluta. Si el modelo devuelve JSON inválido,
el subagente:

- registra una observación;
- conserva el texto libre cuando es útil;
- utiliza un fallback estructural;
- o marca la evidencia como insuficiente.

La ejecución no se descarta silenciosamente.

### Acción forzada del Implementer

El Implementer evita quedarse leyendo indefinidamente.

Cuando el pedido requiere cambios y todavía no hubo escrituras, puede forzar:

```text
tool_choice = write_file
```

También puede exigir una escritura sobre tests cuando el pedido los solicita
explícitamente y todavía no se modificó ningún archivo de pruebas.

## Estado compartido: `TaskState`

El estado central vive en:

```text
task_state.py
```

Se crea una vez por corrida y se comparte entre todos los subagentes.

Campos principales:

### `original_request`

Conserva el pedido original sin modificar.

### `workspace_path`

Identifica el repositorio sobre el cual se trabaja.

### `status`

Estados posibles:

```text
in_progress
done
blocked
needs_help
```

- `done`: tarea completada;
- `blocked`: una política, error técnico o validación impide finalizar;
- `needs_help`: faltan definiciones o el sistema detecta que no debe avanzar.

### `current_phase`

Registra la etapa actual:

```text
exploration
research
implementation
testing
review
```

### `progress_log`

Historial legible con timestamp.

Ejemplo:

```text
Llamando a subagente: explorer
Fase actual: exploration
Tester falló en el intento 1/3
Tarea completada
```

### `subagent_results`

Guarda los resultados por subagente.

Puede contener más de un resultado para Implementer y Tester cuando hubo
reintentos.

### `sources_consulted`

Distingue la procedencia de la información:

```text
repository
memory
rag
web
```

### `files_modified`

Registra los paths detectados como modificados.

Hay dos mecanismos:

1. `write_file` registra directamente el path escrito;
2. después de ciertos comandos, `ToolExecutor` inspecciona `git status` para
   detectar efectos secundarios, como un lint ejecutado con `--fix`.

Este mecanismo es best-effort.

Si el workspace ya tenía cambios sin commit antes de una corrida, esos paths
también pueden aparecer en `files_modified`. Por eso las pruebas finales se
ejecutan preferentemente con un workspace limpio y la atribución se
complementa con `tool_call_history`.

### `observations`

Guarda información adicional:

- errores;
- bloqueos de política;
- repeticiones;
- fallos de parseo;
- feedback del Tester;
- aclaraciones solicitadas.

### `tool_call_history`

Registra cada tool call con:

- subagente;
- tool;
- argumentos;
- resultado;
- duración;
- timestamp.

Se utiliza para:

- auditoría;
- trazabilidad;
- detección de repetición;
- análisis de efectos;
- observabilidad.

### `project_memory`

Referencia al objeto `ProjectMemory` asociado con el workspace.

## Memoria persistente

La memoria se implementa en:

```text
project_memory.py
```

A diferencia de `TaskState`, que pertenece a una ejecución, `ProjectMemory`
sobrevive entre corridas.

Se almacena un archivo JSON por workspace dentro de:

```text
memory/
```

El nombre combina el proyecto con un identificador derivado del path.

La memoria puede conservar:

- arquitectura detectada;
- archivos importantes;
- dependencias;
- comandos útiles;
- decisiones aprobadas;
- bugs investigados;
- bugs resueltos;
- resúmenes de sesiones.

La memoria se actualiza durante la ejecución:

- Explorer aporta información del repositorio;
- Tester confirma comandos útiles;
- el ciclo de reintentos registra bugs;
- una implementación aprobada puede registrar una decisión.

Al finalizar la corrida, el Orchestrator intenta persistirla incluso cuando la
tarea termina bloqueada o en `needs_help`.

Un fallo al guardar memoria no reemplaza el resultado real de la tarea. Se
registra como observación.

## Manejo de contexto en tareas y proyectos extensos

El sistema evita enviar todo el repositorio o todo el historial completo al
modelo en cada llamada.

La estrategia combina varios mecanismos.

### Lectura selectiva del repositorio

Explorer descubre la estructura y lee únicamente archivos relacionados con el
pedido.

Los siguientes subagentes reciben esa selección y pueden realizar
verificaciones puntuales.

No se serializa el repositorio completo dentro del prompt.

### Resultados estructurados

Cada subagente devuelve un `SubagentResult`.

Los subagentes posteriores trabajan con:

- resumen;
- datos relevantes;
- fuentes;
- archivos importantes;
- errores concretos.

No reciben necesariamente toda la conversación interna ni todos los outputs
anteriores.

### Estado centralizado

`TaskState` evita duplicar contexto entre agentes.

Mantiene la información operativa de la tarea en un único objeto compartido.

El historial completo de tools se conserva para auditoría, pero no se agrega
indiscriminadamente a cada prompt.

### Recuperación RAG acotada

El Researcher no recibe toda la documentación.

El Retriever selecciona únicamente los chunks relevantes mediante:

- embedding de la consulta;
- filtro por ecosistema;
- top-k;
- umbral de similitud.

Cada chunk conserva texto, fuente, sección y metadata.

### Memoria por proyecto

`ProjectMemory` permite reutilizar conocimiento entre procesos distintos.

En una nueva corrida puede recuperar:

- arquitectura;
- comandos;
- decisiones;
- archivos importantes;
- bugs anteriores.

La memoria funciona como contexto resumido, no como reproducción completa de
todas las conversaciones históricas.

### Límites de crecimiento

El sistema limita el crecimiento del contexto mediante:

- máximo de iteraciones por subagente;
- número acotado de verificaciones del Researcher;
- top-k del RAG;
- detección de tools repetidas;
- máximo de reintentos;
- fingerprint de errores;
- finalización temprana en `needs_help`.

## Base RAG dentro de la arquitectura

El RAG está compuesto por:

```text
DocumentLoader
MarkdownChunker
OpenAIEmbeddingProvider
ChromaVectorStore
Retriever
rag_search tool
```

Flujo de ingesta:

```text
knowledge_base/raw/
        ↓
DocumentLoader
        ↓
MarkdownChunker
        ↓
OpenAI embeddings
        ↓
ChromaDB persistente
```

Flujo de recuperación:

```text
pedido + contexto del repositorio
        ↓
detección de ecosistema
        ↓
rag_search
        ↓
chunks relevantes
        ↓
evaluación de suficiencia
        ↓
web_search, si corresponde
```

Las fuentes RAG y web se conservan separadas.

## Políticas y seguridad

### `PolicyEngine`

Se implementa en:

```text
policy_engine.py
```

Carga las reglas desde:

```text
agent.config.yaml
```

Valida:

- workspace permitido;
- tools habilitadas;
- paths de lectura;
- paths de escritura;
- comandos prohibidos;
- comandos que requieren aprobación;
- categorías que requieren supervisión.

Ejemplos de operaciones bloqueables:

```text
leer .env
escribir package-lock.json
git push
git reset --hard
rm -rf
sudo
prisma migrate reset
```

### `ToolExecutor`

Se implementa en:

```text
tool_executor.py
```

Es el único componente que ejecuta una tool.

Secuencia:

```text
subagente solicita tool
        ↓
verificación de ALLOWED_TOOLS
        ↓
PolicyEngine.validate
        ↓
aprobación humana, si corresponde
        ↓
ejecución
        ↓
registro en TaskState
        ↓
registro en Langfuse
```

El resultado de una tool puede terminar como:

```text
executed
blocked_by_agent_permissions
blocked_by_policy
denied_by_user
execution_error
```

## Supervisión humana

Las categorías sensibles pueden requerir confirmación por consola.

Ejemplo:

```text
Aprobación requerida
Subagente: implementer
Tool: write_file
Argumentos: {...}
Motivo: La categoría 'write' requiere aprobación.
¿Aprobar? (yes/no):
```

Cuando el usuario rechaza:

```text
outcome = denied_by_user
```

La operación no se ejecuta.

## Comportamiento seguro

### Pedido ambiguo

Cuando el Researcher concluye:

```text
requirements_clear = false
```

el Orchestrator:

- registra las aclaraciones;
- cambia el estado a `needs_help`;
- no llama al Implementer;
- no escribe archivos;
- no ejecuta tests.

### Evidencia insuficiente para implementar

Cuando el Implementer devuelve:

```text
evidence_sufficient = false
```

y no modificó archivos, el sistema lo interpreta como una negativa segura.

La tarea termina en `needs_help`.

### Fallo del Tester

Cuando un check falla:

1. se guardan comando, stdout, stderr y return code;
2. el resultado se entrega al Implementer;
3. el Implementer debe corregir todos los fallos;
4. se vuelve a ejecutar el Tester.

### Loop entre Implementer y Tester

El Orchestrator crea un fingerprint de los checks fallidos.

El fingerprint considera:

- comando;
- return code;
- stderr normalizado.

Se eliminan números variables para evitar que cambios de línea o valores
incidentales hagan parecer distinto el mismo error.

Si dos intentos consecutivos fallan de la misma forma:

- se detecta falta de progreso;
- se termina en `needs_help`;
- se registra una observación;
- no se sigue reintentando a ciegas;
- Reviewer no se ejecuta.

### Workspace inválido

El workspace se valida antes de iniciar el pipeline.

Cuando no coincide con la configuración permitida:

- la tarea termina en `blocked`;
- no se ejecutan tools;
- se evita gastar llamadas innecesarias al modelo.

## Observabilidad

La instrumentación se implementa en:

```text
observability.py
```

Se utiliza Langfuse para registrar una traza por ejecución.

Jerarquía esperada:

```text
coding-agent-run
├── subagent:explorer
│   ├── OpenAI generation
│   ├── tool:list_files
│   └── tool:read_file
├── subagent:researcher
│   ├── tool:rag_search
│   ├── tool:web_search
│   └── OpenAI generation
├── subagent:implementer
│   ├── tool:read_file
│   ├── tool:write_file
│   └── OpenAI generation
├── subagent:tester
│   └── tool:run_command
└── subagent:reviewer
    ├── tool:read_file
    └── OpenAI generation
```

La observabilidad registra:

- pedido;
- modo;
- workspace;
- prompts;
- modelo;
- generaciones;
- tools;
- argumentos sanitizados;
- documentos recuperados;
- búsquedas web;
- resultados;
- errores;
- reintentos;
- latencias;
- tokens;
- costo estimado;
- archivos modificados;
- estado final.

Cuando Langfuse no está configurado, el sistema utiliza una observación no-op
para que el agente siga funcionando.

## Resumen del flujo completo

```text
1. Usuario envía un pedido
2. Orchestrator valida workspace
3. Carga memoria del proyecto
4. Clasifica el request_mode
5. Explorer inspecciona archivos relevantes
6. Researcher consulta RAG y, si corresponde, web
7. Orchestrator evalúa claridad de requisitos
8. Implementer solicita aprobación y escribe
9. Tester ejecuta checks reales
10. Si falla, Implementer corrige
11. Reviewer compara resultado y pedido
12. Orchestrator define done, blocked o needs_help
13. Guarda memoria
14. Finaliza la traza de Langfuse
15. Devuelve TaskState como JSON
```

## Principios de diseño

La arquitectura se apoya en los siguientes principios:

- separación clara de responsabilidades;
- privilegio mínimo por subagente;
- estado compartido y trazable;
- herramientas controladas por política;
- supervisión humana para escrituras;
- RAG antes de web;
- memoria persistente por proyecto;
- contexto selectivo y resumido;
- validación con herramientas reales;
- reintentos acotados;
- detección de loops;
- detención segura ante ambigüedad;
- revisión contra el pedido original;
- observabilidad externa de extremo a extremo.