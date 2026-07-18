# Observabilidad con Langfuse

## Objetivo

El coding agent integra **Langfuse** para registrar y visualizar ejecuciones completas del sistema multiagente.

La observabilidad no se limita a guardar la respuesta final. Cada tarea queda representada como una traza jerárquica que permite reconstruir:

- el pedido original;
- el modo de ejecución detectado;
- los subagentes ejecutados;
- los prompts enviados al modelo;
- el modelo y los parámetros utilizados;
- las llamadas al LLM;
- las tools invocadas;
- las fuentes obtenidas desde repositorio, memoria, RAG o web;
- los archivos modificados;
- las iteraciones y reintentos;
- los errores encontrados;
- las validaciones ejecutadas;
- la latencia, los tokens y el costo estimado;
- el resultado final de la tarea.

La evidencia visual incluida en este entregable corresponde a una traza completa de una tarea de implementación sobre el repositorio `issue-tracker-api`.

---

## Herramienta elegida

Se utilizó **Langfuse** como plataforma de observabilidad.

La integración se encuentra centralizada en:

```text
observability.py
```

y es utilizada desde:

```text
main.py
orchestrator.py
tool_executor.py
```

Las llamadas al modelo realizadas dentro de los spans aparecen en Langfuse como observaciones `OpenAI-generation`, con el prompt, el modelo, la respuesta, la latencia, los tokens y el costo estimado de cada generación.

---

## Configuración

La observabilidad se habilita cuando están definidas las siguientes variables en el archivo `.env` del proyecto:

```env
LANGFUSE_PUBLIC_KEY=...
LANGFUSE_SECRET_KEY=...
LANGFUSE_BASE_URL=...
```

La clase `Observability` verifica la presencia de las tres variables antes de crear el cliente.

Cuando Langfuse no está configurado, el sistema utiliza `NoOpObservation`. De esta manera, el coding agent y sus tests pueden ejecutarse sin credenciales y sin tener que duplicar lógica condicional en el orquestador, los subagentes o el ejecutor de tools.

En `main.py`, el envío de observaciones pendientes se fuerza dentro de un bloque `finally`:

```python
finally:
    get_observability().flush()
```

Esto permite que las trazas se envíen antes de finalizar el proceso, incluso si la ejecución termina con una excepción.

---

## Estructura de una traza

La instrumentación representa cada ejecución mediante tres niveles principales.

### 1. Span raíz de la ejecución

Cada pedido crea una observación raíz llamada:

```text
coding-agent-run
```

El span se crea mediante `run_span()` y registra como entrada:

- `user_request`;
- `workspace`;
- `request_mode`.

También se asigna una sesión estable por proyecto. El identificador se construye a partir de un hash SHA-256 de la ruta absoluta del workspace, evitando utilizar la ruta completa como identificador visible.

Al finalizar, el span raíz registra:

- estado final;
- fase actual;
- fuentes consultadas;
- archivos modificados;
- iteraciones por subagente;
- observaciones y errores relevantes;
- subagentes ejecutados;
- modo de la tarea.

En Langfuse también quedan disponibles las métricas agregadas de duración, tokens y costo de la traza.

### 2. Spans de subagentes

Cada llamada a un subagente crea un span con el formato:

```text
subagent:explorer
subagent:researcher
subagent:implementer
subagent:tester
subagent:reviewer
```

Estos spans se crean desde `Orchestrator.call_subagent()` y registran:

- nombre del subagente;
- fase;
- modo de la tarea;
- resumen del resultado;
- fuentes utilizadas;
- cantidad de iteraciones;
- datos producidos por el subagente.

Las llamadas al modelo y las tools utilizadas durante esa fase quedan anidadas dentro del span correspondiente. Esto permite distinguir claramente qué agente tomó cada decisión o ejecutó cada acción.

### 3. Spans de tools

Cada tool se registra como una observación de tipo `tool`, con nombres como:

```text
tool:list_files
tool:read_file
tool:write_file
tool:run_command
tool:rag_search
tool:web_search
```

El `ToolExecutor` crea el span antes de validar y ejecutar la operación. Por eso, además de las ejecuciones exitosas, también pueden registrarse:

- tools bloqueadas por permisos del subagente;
- tools bloqueadas por políticas globales;
- operaciones que requerían aprobación;
- operaciones rechazadas por el usuario;
- errores de ejecución;
- duración;
- resultado de la tool.

Para las tools sensibles se incluyen metadatos como:

- `approvalrequired`;
- `approvedbyuser`;
- `outcome`;
- subagente responsable.

---

## Registro de RAG y búsqueda web

Las tools `rag_search` y `web_search` reciben un tratamiento especial.

En ambos casos se conserva el resultado estructurado para que Langfuse pueda mostrar:

- consulta realizada;
- cantidad de resultados solicitados;
- documentos o páginas recuperadas;
- secciones;
- identificadores de chunks;
- similitud;
- fuentes y enlaces, cuando corresponda;
- duración de la recuperación.

En la traza principal documentada en este archivo, el Researcher determinó que la evidencia del repositorio y del RAG era suficiente:

```text
needs_web_fallback: false
used_web_fallback: false
```

Por ese motivo no se ejecutó una búsqueda web en esa tarea. Esta ausencia no corresponde a un error: demuestra que el agente respeta la estrategia de consultar primero el RAG y recurrir a la web únicamente cuando la evidencia previa no alcanza.

La instrumentación de `web_search` queda preparada en `build_tool_output()` para conservar sus fuentes de la misma manera que en `rag_search`.

---

## Sanitización y protección de la información registrada

Antes de enviar datos a Langfuse, la implementación limita la profundidad y el tamaño de las estructuras.

Las principales medidas son:

- strings limitados a 4000 caracteres;
- colecciones limitadas a 30 elementos;
- profundidad máxima de seis niveles;
- truncado de comandos demasiado largos;
- en `write_file`, registro de cantidad de caracteres y una vista previa, en lugar de guardar siempre el archivo completo;
- en `read_file`, registro de cantidad de caracteres y una vista previa de hasta 500 caracteres;
- en `list_files`, registro de cantidad de entradas y una lista limitada;
- conservación estructurada de las fuentes para RAG y web.

Esto permite mantener trazas útiles sin cargar archivos completos, resultados excesivos o información innecesaria.

---

# Traza seleccionada para la evidencia

## Identificador

```text
0a5275dd9f84bba4d6e7d945cfbf8546
```

## Tarea ejecutada

La tarea solicitó ampliar la cobertura unitaria de `TicketsService`:

> Ampliar la cobertura unitaria de `TicketsService` modificando `src/tickets/tickets.service.spec.ts`. Mantener los tests existentes y agregar casos que verifiquen `findAll`, `findOne` y `delete`, actualizar los mocks de `PrismaService` y no modificar endpoints ni el schema de Prisma.

El modo detectado fue:

```text
implementation
```

## Métricas generales de la traza

Langfuse registró:

```text
Duración total: 5 min 35 s
Prompt tokens: 275.415
Completion tokens: 43.735
Tokens totales: 319.150
Costo estimado: USD 0,020594
Estado final: done
```

Durante las generaciones mostradas en las capturas se utilizó el modelo:

```text
gpt-5-nano-2025-08-07
```

---

# Historia de la ejecución

## 1. Inicio y exploración del repositorio

La traza comienza en el span raíz `coding-agent-run`, que registra el pedido original, el workspace `issue-tracker-api` y el modo `implementation`.

El Explorer inspeccionó la estructura del repositorio mediante `list_files` y leyó los archivos relevantes mediante `read_file`.

La fase finalizó con:

```text
10 iteraciones
6 archivos leídos
```

Entre los archivos analizados se encontraron:

```text
src/tickets/tickets.service.ts
src/tickets/tickets.service.spec.ts
src/tickets/dto/find-tickets.dto.ts
src/tickets/dto/create-ticket.dto.ts
src/prisma/prisma.service.ts
src/tickets/tickets.controller.ts
```

El resultado del Explorer permitió identificar que el proyecto utiliza TypeScript, NestJS y Prisma, y que la tarea debía concentrarse en el servicio y en su archivo de pruebas.

## 2. Investigación con repositorio y RAG

El Researcher recibió los hallazgos del Explorer y consultó primero el RAG mediante:

```text
tool:rag_search
```

La consulta solicitó cuatro resultados y produjo además una observación hija de embedding.

Se recuperaron cuatro fragmentos del documento interno:

```text
jest/testing-and-linting.md
```

Las secciones utilizadas incluyeron:

- tipado en tests TypeScript;
- mocks de Jest;
- conservación de tests existentes;
- recomendaciones relacionadas con Jest y lint.

Los resultados conservaron `chunk_id`, sección, similitud y fuente. El Researcher concluyó:

```text
evidence_sufficient: true
requirements_clear: true
needs_web_fallback: false
used_web_fallback: false
```

Por lo tanto, continuó con evidencia del repositorio y del RAG sin ejecutar una búsqueda web innecesaria.

## 3. Primer intento de implementación

El primer Implementer utilizó los hallazgos del Explorer, las recomendaciones del Researcher y la memoria persistente del proyecto.

La fase registró:

```text
11 iteraciones
2 archivos modificados
```

Los archivos afectados fueron:

```text
src/tickets/tickets.service.spec.ts
src/tickets/tickets.service.ts
```

El cambio amplió los mocks y agregó casos para:

- `findAll()` sin filtro;
- `findAll()` con estado `OPEN`;
- `findOne()` cuando el ticket existe;
- `findOne()` cuando el ticket no existe;
- `delete()` cuando el ticket existe;
- `delete()` cuando el ticket no existe.

Las operaciones de escritura fueron ejecutadas mediante `tool:write_file` y requirieron aprobación humana según las políticas del agente.

## 4. Primera validación y error detectado

Después de la implementación, el Tester ejecutó:

```text
npx prisma validate
npm run lint
npm run build
npm run test
```

Los resultados fueron:

```text
Prisma validate: OK
Build: OK
Tests: OK
Lint: ERROR
```

Jest informó:

```text
Test Suites: 2 passed, 2 total
Tests: 9 passed, 9 total
```

Sin embargo, `npm run lint` devolvió código `1` y detectó once problemas:

```text
7 errores
4 warnings
```

Los principales problemas fueron:

- uso inseguro de `any`;
- asignaciones no seguras;
- formato incompatible con Prettier;
- importación de `Prisma` declarada pero no utilizada.

Este error quedó registrado en el resultado del Tester y en las observaciones del estado compartido.

## 5. Reintento del Implementer

El orquestador detectó que el primer Tester no había aprobado todos los checks y volvió a llamar al Implementer.

La secuencia registrada fue:

```text
Implementer → Tester con error → Implementer
```

El segundo intento utilizó el feedback autoritativo del Tester para corregir los problemas de tipado y formato.

La fase registró:

```text
14 iteraciones
2 archivos modificados
```

Entre las correcciones realizadas se incluyeron:

- reemplazo de usos de `any`;
- uso de `FindTicketsDto`;
- uso de `TicketStatus.OPEN`;
- ajuste de tipos de Prisma;
- eliminación del import no utilizado;
- correcciones de formato compatibles con ESLint y Prettier.

## 6. Validación final

Después del reintento, el Tester volvió a ejecutar los cuatro checks:

```text
npx prisma validate
npm run lint
npm run build
npm run test
```

En el segundo ciclo todos finalizaron correctamente:

```text
all_passed: true
```

Los tests volvieron a informar:

```text
Test Suites: 2 passed, 2 total
Tests: 9 passed, 9 total
```

Esta segunda validación demuestra que el sistema no ocultó el error ni terminó después de verificar solamente los tests. El pipeline exigió también que Prisma, lint y build quedaran correctos.

## 7. Revisión final

El Reviewer leyó los dos archivos modificados y comparó:

- el pedido original;
- los cambios declarados por el Implementer;
- los archivos realmente modificados;
- el resultado del Tester.

La revisión terminó con:

```text
approved: true
matches_request: true
issues: []
```

El Reviewer confirmó que:

- se mantuvieron los tests existentes;
- se agregaron los casos pedidos;
- se ajustaron los mocks de Prisma;
- se evitaron usos inseguros de `any`;
- lint, build y tests quedaron correctos;
- no se modificaron endpoints ni el schema de Prisma.

Finalmente, el span raíz quedó con:

```text
status: done
current_phase: review
sources_consulted: repository, memory, rag
```

---

# Capturas incluidas

Las capturas se presentan en el siguiente orden para reconstruir la ejecución de principio a fin.

| N.º | Archivo                                    | Evidencia mostrada |
|----:|--------------------------------------------|---|
|   1 | `01_trace-overview.png`                    | Pedido original, duración, tokens, costo, fuentes, archivos modificados y estado final. |
|   2 | `02_researcher_fuentes_y_decision.png`     | Resultado del Researcher, suficiencia de evidencia y decisión de no usar fallback web. |
|   3 | `03_rag_search_consulta.png`               | Invocación de `rag_search`, consulta, cantidad de resultados y latencia. |
|   4 | `04_rag_documentos_recuperados.png`        | Documentos y chunks recuperados, secciones y similitud. |
|   5 | `05_researcher_prompt_modelo_metricas.png` | Prompt del Researcher, modelo, llamada al LLM, tokens, latencia y costo. |
|   6 | `06_implementer_primer_intento.png`        | Primer resultado del Implementer, fuentes, iteraciones y archivos modificados. |
|   7 | `07_implementer_prompt_modelo_tools.png`   | Prompt, modelo y reglas operativas del Implementer. |
|   8 | `08_tester_lint_fallido.png`               | Error de lint del primer ciclo y código de retorno fallido. |
|   9 | `09_implementer_reintento_correccion.png`  | Segundo intento del Implementer a partir del feedback del Tester. |
|  10 | `10_tester_tests_aprobados.png`            | Ejecución de Jest con dos suites y nueve tests aprobados. |
|  11 | `11_reviewer_prompt_y_tools.png`           | Prompt, modelo y tools utilizadas por el Reviewer. |
|  12 | `12_reviewer_resultado_aprobado.png`       | `approved: true`, `matches_request: true`, archivos revisados y ausencia de issues. |

---

# Correspondencia con la consigna

| Requisito de observabilidad | Registro realizado |
|---|---|
| Prompts | Visibles dentro de cada observación `OpenAI-generation`, incluyendo mensajes de sistema y entradas de los subagentes. |
| Modelo utilizado | Registrado en cada generación; en la traza seleccionada se observa `gpt-5-nano-2025-08-07`. |
| Llamadas al LLM | Cada generación aparece como una observación hija dentro del subagente que la produjo. |
| Tools invocadas | Registradas como `tool:list_files`, `tool:read_file`, `tool:write_file`, `tool:run_command` y `tool:rag_search`. |
| Documentos recuperados | El resultado de `rag_search` conserva fuentes, títulos, secciones, chunks y similitud. |
| Búsquedas web | `tool:web_search` está instrumentada y conserva resultados estructurados. En esta traza no fue necesaria porque el RAG produjo evidencia suficiente. |
| Iteraciones | Registradas por subagente y mostradas en sus outputs y en el resultado raíz. |
| Errores | El primer `npm run lint` fallido quedó registrado con salida, código de retorno y detalle de problemas. |
| Latencia | Disponible en la traza, en cada subagente, cada tool y cada generación. |
| Tokens | Registrados por generación y agregados en el span raíz. |
| Costo estimado | Visible por generación, por subagente y para la ejecución completa. |
| Resultado final | El span raíz registra `status: done`; el Reviewer registra `approved: true` y `matches_request: true`. |

---

## Conclusión

La integración con Langfuse permite observar la ejecución real del coding agent, no solamente su salida final.

La traza seleccionada resulta representativa porque muestra:

```text
pedido
→ exploración del repositorio
→ recuperación RAG
→ primera implementación
→ validación con error
→ reintento y corrección
→ validaciones exitosas
→ revisión aprobada
→ estado final done
```

La evidencia demuestra coordinación entre subagentes, uso de tools, utilización de memoria y RAG, supervisión humana para escrituras, detección de errores, reintento con feedback y validación final verificable.