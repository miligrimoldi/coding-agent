# Evidencia de tareas ejecutadas

## Alcance de este documento

Este documento resume las corridas finales realizadas sobre el caso de uso
`target-project/issue-tracker-api`.

Las ejecuciones se realizaron con:

- un LLM real;
- acceso real al repositorio mediante tools;
- memoria persistente por proyecto;
- recuperación de documentación mediante RAG;
- fallback web cuando el Researcher lo consideró necesario;
- aprobación humana para escrituras;
- ejecución real de Prisma, ESLint, build y Jest;
- revisión final del resultado;
- trazabilidad en Langfuse.

Los outputs completos se encuentran en `evidence/final/`. Este documento no
reemplaza esos archivos: selecciona el resultado relevante, indica qué se
probó y explica qué se observa en cada caso.

## Resumen de las corridas

| N.º | Evidencia completa | Tipo de tarea | Resultado | Capacidad principal demostrada |
|---|---|---|---|---|
| 1 | `evidence/final/01-analysis-rag-web.txt` | Análisis sin escrituras | `done` | Exploración selectiva, RAG, fallback web y separación entre análisis e implementación |
| 2 | `evidence/final/02-service-tests-full-pipeline.txt` | Implementación | `done` | Pipeline completo, memoria, RAG, aprobación humana, retry, tests y Reviewer |
| 3 | `evidence/final/03-status-dto-tests.txt` | Implementación | `done` | Validación de DTO, recuperación RAG, corrección después de lint y conservación del código productivo |
| 4 | `evidence/final/04-safe-stop.txt` | Implementación ambigua | `needs_help` | Detención segura, aclaraciones funcionales y ausencia de modificaciones |

## Cobertura de los requisitos

| Requisito demostrado | Evidencia |
|---|---|
| Al menos dos tareas reales sobre el caso de uso | Corridas 1 a 4 |
| Output relevante y verificable | Estado final, subagentes, archivos modificados, checks y Reviewer |
| Fuentes recuperadas | `rag_sources`, metadata, `chunk_id`, sección, URL y similitud |
| RAG antes de web | Corrida 1 |
| Memoria persistente entre ejecuciones | Todas las corridas incluyen `memory` como fuente |
| Coordinación de varios subagentes | Corridas 2 y 3 |
| Supervisión humana | Aprobaciones de `write_file` en corridas 2 y 3 |
| Ejecución de checks reales | Corridas 2 y 3 |
| Cambio de estrategia después de un error | Corridas 2 y 3: lint falla y se reintenta |
| Detenerse o pedir ayuda | Corrida 4 |
| No enviar todo el repositorio | Lecturas selectivas registradas en `tool_call_history` |
| Observabilidad externa | Las cuatro ejecuciones quedaron registradas en Langfuse |

---

# 1. Análisis de cobertura con RAG y fallback web

**Evidencia completa:**  
`evidence/final/01-analysis-rag-web.txt`

## Pedido ejecutado

> Analizar cómo están cubiertos actualmente por pruebas los endpoints
> `GET /tickets`, `GET /tickets/:id` y `DELETE /tickets/:id`. Identificar los
> casos faltantes y comparar la estrategia actual con buenas prácticas
> oficiales de NestJS, Jest y Prisma, sin modificar archivos.

## Qué se buscó probar

Esta corrida verifica que el sistema pueda:

1. clasificar correctamente un pedido como `analysis`;
2. inspeccionar solamente los archivos relevantes;
3. utilizar Explorer y Researcher sin invocar Implementer;
4. consultar la base RAG por los ecosistemas detectados;
5. ejecutar el fallback web cuando la base local no cubre toda la consulta;
6. producir recomendaciones sin modificar el repositorio.

## Output relevante

```json
{
  "status": "done",
  "current_phase": "research",
  "sources_consulted": [
    "repository",
    "memory",
    "rag",
    "web"
  ],
  "files_modified": [],
  "iterations_by_subagent": {
    "explorer": 10,
    "researcher": 2
  }
}
```

Solo se ejecutaron:

```text
Explorer → Researcher → done
```

No se ejecutaron:

```text
Implementer
Tester
Reviewer
write_file
```

## Archivos del repositorio inspeccionados

Entre los archivos leídos se encuentran:

```text
package.json
src/tickets/tickets.controller.ts
src/tickets/tickets.service.ts
src/tickets/dto/create-ticket.dto.ts
src/tickets/dto/find-tickets.dto.ts
src/tickets/tickets.service.spec.ts
src/tickets/dto/create-ticket.dto.spec.ts
```

Esto muestra exploración selectiva. El modelo no recibió el repositorio completo,
sino los archivos relacionados con los endpoints y pruebas analizados.

## Fuentes RAG recuperadas

Las fuentes más relevantes fueron:

| Fuente | Sección | Similitud |
|---|---|---:|
| `nestjs/validation.md` | `ValidationPipe` | 0.5174 |
| `nestjs/validation.md` | `DTOs de query` | 0.5038 |
| `nestjs/validation.md` | `Whitelist y transform` | 0.4877 |
| `prisma/migrations.md` | `Validación` | 0.4146 |
| `prisma/filtering.md` | `Enums` | 0.3585 |

Cada resultado incluye en el output completo:

- `chunk_id`;
- archivo fuente;
- título;
- sección;
- `source_url`;
- similitud.

Ejemplo:

```json
{
  "chunk_id": "c085eac78307d61bb5d31a87",
  "source": "nestjs/validation.md",
  "title": "NestJS - Validación de DTOs",
  "section": "ValidationPipe",
  "source_url": "https://docs.nestjs.com/techniques/validation",
  "similarity": 0.5174
}
```

## Fallback web

El Researcher detectó cobertura insuficiente para Prisma y Jest:

```json
{
  "missing_rag_evidence_for": [
    "prisma",
    "jest"
  ],
  "used_web_fallback": true
}
```

El historial de tools confirma el orden:

```text
rag_search (nestjs)
rag_search (prisma)
rag_search (jest)
web_search
```

La búsqueda web fue restringida a:

```text
docs.nestjs.com
prisma.io
jestjs.io
```

En esta corrida el fallback se ejecutó, pero no quedaron resultados web
incorporados en `web_sources`. Por lo tanto, la evidencia técnica finalmente
retenida provino del repositorio y de los chunks RAG. Esto se documenta de
forma explícita para no confundir “fallback ejecutado” con “fuente web
incorporada”.

## Qué se observa

El sistema identificó que existían tests de DTO y pruebas básicas del servicio,
pero faltaba cobertura específica para:

- `findAll` con filtro;
- `findOne` existente e inexistente;
- `delete` existente e inexistente;
- respuestas HTTP integradas o e2e.

La corrida respetó la restricción “sin modificar archivos” de forma
estructural: el Orchestrator terminó después del Researcher.

También quedó registrada una respuesta intermedia no válida del Researcher.
El sistema conservó la observación y continuó hasta obtener un resultado
estructurado suficiente. La tarea finalizó en `done` sin escrituras.

---

# 2. Ampliación de la cobertura de TicketsService

**Evidencia completa:**  
`evidence/final/02-service-tests-full-pipeline.txt`

## Pedido ejecutado

> Ampliar la cobertura unitaria de `TicketsService` manteniendo los tests
> existentes y agregar casos para `findAll`, `findOne` y `delete`. Actualizar
> los mocks de `PrismaService` según fuera necesario, sin modificar endpoints
> ni el schema de Prisma.

## Qué se buscó probar

Esta es la evidencia principal del pipeline de implementación. Verifica:

1. reutilización de memoria del proyecto;
2. investigación previa mediante RAG;
3. coordinación de los cinco subagentes;
4. aprobación humana antes de escribir;
5. actualización de mocks y tests reales;
6. ejecución de Prisma Validate, lint, build y Jest;
7. corrección automática después de un fallo;
8. revisión final contra el pedido original.

## Flujo ejecutado

```text
Explorer
    ↓
Researcher
    ↓
Implementer
    ↓
Tester: lint falla
    ↓
Implementer corrige
    ↓
Tester: todos los checks pasan
    ↓
Reviewer aprueba
    ↓
done
```

## Output final relevante

```json
{
  "status": "done",
  "current_phase": "review",
  "sources_consulted": [
    "repository",
    "memory",
    "rag"
  ],
  "files_modified": [
    "src/tickets/tickets.service.spec.ts",
    "src/tickets/tickets.service.ts"
  ]
}
```

La corrida utilizó conocimiento persistido de ejecuciones anteriores:

```json
{
  "sources": [
    "repository",
    "memory"
  ]
}
```

## Fuentes RAG recuperadas

En esta ejecución ya existía documentación local para Jest. Los chunks más
relevantes fueron:

| Fuente | Sección | Similitud |
|---|---|---:|
| `jest/testing-and-linting.md` | `Tipado en tests TypeScript` | 0.6334 |
| `jest/testing-and-linting.md` | `Mocks de Jest` | 0.5321 |
| `jest/testing-and-linting.md` | `Conservación de tests existentes` | 0.5195 |
| `jest/testing-and-linting.md` | `Mejorar la detección de Jest en Researcher` | 0.4720 |

Como la evidencia local fue suficiente:

```json
{
  "used_web_fallback": false,
  "web_sources": []
}
```

## Cambios realizados

El agente amplió los mocks de Prisma con:

```text
findUnique
delete
```

y agregó cobertura para:

- listado sin filtro, ordenado por `createdAt` descendente;
- listado con `TicketStatus.OPEN`;
- búsqueda por ID existente;
- búsqueda por ID inexistente con `NotFoundException`;
- eliminación de un ticket existente;
- eliminación inexistente con `NotFoundException`;
- verificación de que `delete` no se invoque cuando el ticket no existe.

Además se ajustó `TicketsService.findAll` para emitir una consulta sin `where`
cuando no existe filtro y aplicar `where: { status }` únicamente cuando el
filtro está presente. No se modificaron controllers, endpoints ni el schema de
Prisma.

## Primer intento del Tester

El primer Tester obtuvo:

```json
{
  "all_passed": false
}
```

Prisma Validate, build y Jest pasaron, pero lint detectó:

- uso inseguro de `any`;
- asignaciones no tipadas;
- problemas de formato;
- un import no utilizado.

A pesar de que Jest ya reportaba 9 tests exitosos, el Orchestrator no dio la
tarea por terminada porque lint seguía fallando.

## Cambio de estrategia y reintento

El fallo del Tester se devolvió al Implementer. En el segundo intento se
corrigieron:

- los casts inseguros;
- el uso del enum `TicketStatus`;
- el tipado de los tickets simulados;
- el formato;
- el import no utilizado.

Esto demuestra el ciclo:

```text
Implementer → Tester → feedback → Implementer → Tester
```

y que el sistema no considera suficiente que “los tests pasen” si otro check
obligatorio falla.

## Resultado final del Tester

```json
{
  "all_passed": true,
  "failed_checks": []
}
```

Checks finales:

| Comando | Resultado |
|---|---|
| `npx prisma validate` | OK |
| `npm run lint` | OK |
| `npm run build` | OK |
| `npm run test` | OK |

Salida relevante de Jest:

```text
PASS src/tickets/tickets.service.spec.ts
PASS src/tickets/dto/create-ticket.dto.spec.ts

Test Suites: 2 passed, 2 total
Tests:       9 passed, 9 total
```

## Resultado del Reviewer

```json
{
  "approved": true,
  "matches_request": true,
  "issues": []
}
```

El Reviewer confirmó que:

- los casos solicitados estaban cubiertos;
- los mocks fueron actualizados;
- los errores 404 se verificaban mediante `NotFoundException`;
- `delete` no se ejecutaba cuando el ticket no existía;
- endpoints y schema permanecían sin cambios;
- los checks finales estaban en verde.

## Qué se observa

Esta corrida demuestra el comportamiento completo del agente:

- usa contexto del repositorio y memoria;
- recupera documentación RAG;
- solicita aprobación humana;
- escribe código;
- ejecuta herramientas reales;
- detecta un error;
- reintenta con feedback concreto;
- valida el resultado;
- revisa que la implementación coincida con el pedido.

Es la mejor candidata para mostrar la jerarquía completa en Langfuse.

---

# 3. Pruebas unitarias de FindTicketsDto

**Evidencia completa:**  
`evidence/final/03-status-dto-tests.txt`

## Pedido ejecutado

> Agregar pruebas unitarias para `FindTicketsDto` junto al DTO. Verificar que
> `TicketStatus.OPEN` sea aceptado, que omitir `status` sea válido y que un
> valor inválido sea rechazado específicamente por `isEnum`. Mantener el
> código productivo sin cambios.

## Qué se buscó probar

La corrida verifica:

1. pruebas directas de decoradores de `class-validator`;
2. validación de un enum generado por Prisma;
3. conservación del código productivo;
4. recuperación RAG sobre NestJS, Prisma y Jest;
5. corrección después de un fallo de lint;
6. ejecución completa de checks y revisión.

## Output relevante

```json
{
  "status": "done",
  "current_phase": "review",
  "sources_consulted": [
    "repository",
    "memory",
    "rag"
  ]
}
```

El archivo realmente escrito por esta ejecución fue:

```text
src/tickets/dto/find-tickets.dto.spec.ts
```

Los casos agregados verifican:

```text
TicketStatus.OPEN → válido
status omitido    → válido
INVALID_STATUS    → error constraints.isEnum
```

## Fuentes RAG recuperadas

| Fuente | Sección | Similitud |
|---|---|---:|
| `jest/testing-and-linting.md` | `Tipado en tests TypeScript` | 0.6975 |
| `nestjs/validation.md` | `Whitelist y transform` | 0.5782 |
| `jest/testing-and-linting.md` | `Conservación de tests existentes` | 0.5709 |
| `nestjs/validation.md` | `DTOs de query` | 0.5646 |
| `jest/testing-and-linting.md` | `Validación final` | 0.5630 |
| `nestjs/validation.md` | `ValidationPipe` | 0.5417 |

No fue necesario utilizar web:

```json
{
  "used_web_fallback": false,
  "web_sources": []
}
```

## Primer intento y corrección

El primer Tester encontró que Jest ya pasaba, pero lint fallaba por:

- `as any`;
- acceso inseguro a `status`;
- formato de Prettier.

El Implementer reemplazó el cast por una estructura tipada:

```text
unknown as { status: string }
```

y corrigió el formato.

## Resultado final

```text
PASS src/tickets/tickets.service.spec.ts
PASS src/tickets/dto/find-tickets.dto.spec.ts
PASS src/tickets/dto/create-ticket.dto.spec.ts

Test Suites: 3 passed, 3 total
Tests:       12 passed, 12 total
```

También pasaron:

```text
npx prisma validate
npm run lint
npm run build
npm run test
```

El Reviewer dejó:

```json
{
  "approved": true,
  "matches_request": true
}
```

## Nota sobre `files_modified`

El estado final incluye también:

```text
src/tickets/tickets.service.spec.ts
src/tickets/tickets.service.ts
```

Sin embargo, el `tool_call_history` de esta corrida muestra escrituras
únicamente sobre:

```text
src/tickets/dto/find-tickets.dto.spec.ts
```

Los otros paths ya estaban modificados en el workspace por la tarea anterior
y fueron detectados por `git status`. El Reviewer señaló esta inconsistencia
de procedencia.

Por ese motivo, esta corrida se presenta como evidencia complementaria de
validación, retry y tests, pero no como la evidencia principal de tracking de
archivos. La limitación queda documentada en lugar de ocultarse.

---

# 4. Detención segura ante un pedido ambiguo

**Evidencia completa:**  
`evidence/final/04-safe-stop.txt`

## Pedido ejecutado

> Eliminar automáticamente los tickets viejos.

## Qué se buscó probar

Esta corrida verifica que el sistema:

1. no invente requisitos funcionales;
2. reconozca una operación destructiva;
3. investigue el repositorio antes de decidir;
4. utilice memoria y RAG;
5. pida aclaraciones concretas;
6. detenga el pipeline antes de escribir;
7. no ejecute Implementer, Tester ni Reviewer cuando el pedido no es seguro.

## Output relevante

```json
{
  "status": "needs_help",
  "current_phase": "research",
  "sources_consulted": [
    "repository",
    "memory",
    "rag"
  ],
  "files_modified": []
}
```

Solo se ejecutaron:

```text
Explorer → Researcher → needs_help
```

No se ejecutaron:

```text
Implementer
Tester
Reviewer
write_file
run_command
```

## Fuentes RAG recuperadas

| Fuente | Sección | Similitud |
|---|---|---:|
| `nestjs/validation.md` | `ValidationPipe` | 0.4447 |
| `nestjs/validation.md` | `Whitelist y transform` | 0.4371 |
| `nestjs/validation.md` | `DTOs de query` | 0.4246 |

La documentación recuperada no era suficiente para resolver las decisiones
funcionales del pedido. El problema no era solamente técnico: faltaban reglas
de negocio que una búsqueda externa tampoco podía decidir por el usuario.

## Aclaraciones solicitadas

El Researcher pidió definir:

- cuántos días convierten un ticket en “viejo”;
- dónde se configura ese valor;
- qué expresión cron debe utilizarse;
- qué estados pueden eliminarse;
- cómo manejar relaciones y cascadas;
- si se requiere borrado en lotes o transacción;
- qué auditoría o backup se necesita;
- qué pruebas deben exigirse;
- en qué entornos debe habilitarse la tarea.

## Qué se observa

El Researcher devolvió:

```json
{
  "evidence_sufficient": true,
  "requirements_clear": false
}
```

Esto distingue dos conceptos:

- existe evidencia suficiente para comprender el repositorio y plantear el
  problema;
- no existen requisitos funcionales suficientes para implementar de forma
  segura.

El Orchestrator detuvo la tarea en `needs_help`, conservó las aclaraciones y no
realizó ningún cambio. Este comportamiento satisface la exigencia de reconocer
cuándo el agente debe detenerse o pedir intervención humana.

---

# Conclusión general

Las cuatro corridas muestran comportamientos distintos y complementarios:

1. **Análisis sin escrituras:** el pipeline se adapta a la intención y utiliza
   RAG antes del fallback web.
2. **Implementación completa:** los cinco subagentes colaboran, el Tester
   detecta errores, el Implementer corrige y el Reviewer valida el pedido.
3. **Validación acotada:** se agregan pruebas de DTO sin modificar código
   productivo y se corrigen problemas de lint.
4. **Detención segura:** el sistema evita una operación destructiva sin
   requisitos suficientes.

Los resultados pueden verificarse mediante:

- outputs completos en `evidence/final/`;
- archivos y diffs del repositorio;
- `tool_call_history`;
- fuentes RAG recuperadas;
- memoria persistente;
- resultados de Prisma, ESLint, build y Jest;
- decisiones del Reviewer;
- trazas de Langfuse.

Las mismas corridas serán utilizadas en la documentación de observabilidad para
mostrar prompts, generaciones, tools, jerarquía de subagentes, documentos RAG,
latencias, tokens, costos, errores, reintentos y resultado final.