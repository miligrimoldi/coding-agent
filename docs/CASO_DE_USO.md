# Caso de uso

## Ecosistema elegido

**NestJS + Prisma + Jest** (TypeScript). Se eligió este stack porque es
representativo de un backend real moderno: framework con inyección de
dependencias y decorators, ORM con generación de tipos y migraciones, y
testing integrado — suficiente superficie para ejercitar exploración de
código, RAG especializado por ecosistema, generación de código con
validaciones, y ejecución de checks reales (build/lint/test).

## Repositorio objetivo

`target-project/issue-tracker-api`: una API REST de tickets, construida
para este TP como base sobre la que trabaja el agente. Stack: NestJS 11,
`@prisma/client` 7 sobre SQLite, `class-validator`/`class-transformer` para
DTOs, Jest para tests unitarios. Al arrancar el proyecto solo tenía
`POST /tickets` y `GET /tickets`, con un modelo `Ticket` (`id`, `title`,
`description`, `status: TicketStatus`, `createdAt`, `updatedAt`).

## Objetivo concreto

Hacer evolucionar la API de tickets agregándole funcionalidad real, de a
una tarea por vez, verificando en cada caso que:

1. El código compile (`npx prisma validate`, `npm run build`).
2. Pase lint sin errores (`npm run lint`).
3. Pase los tests existentes y, cuando el pedido lo requiere explícitamente,
   que se agreguen tests nuevos para lo agregado.
4. El Reviewer confirme que los archivos efectivamente modificados
   corresponden a lo que pidió el usuario (no solo que "algo" haya pasado
   los checks).

Esto no es "probar que el agente funciona" en abstracto: cada corrida deja
un diff real y verificable sobre un proyecto NestJS real, ejecutando sus
propias herramientas (Prisma, ESLint, Jest), no una simulación.

## Funcionalidad agregada durante el desarrollo

A lo largo de varias corridas reales (ver `docs/EVIDENCIA.md`), el agente
fue agregando:

- `GET /tickets` con filtro opcional por `status` (query param validado
  contra el enum `TicketStatus`).
- `GET /tickets/:id`, con 404 si el ticket no existe.
- `DELETE /tickets/:id`, con 404 si no existe y 204 si se borra.
- Límite de longitud (`MaxLength(120)`) en el título al crear un ticket,
  manteniendo la validación mínima existente, con sus tests unitarios
  correspondientes.

Además de tareas que el agente correctamente **no** completó (y debía no
completar): un pedido de borrado automático de tickets viejos sin definir
la política de retención (`needs_help` — faltaba información), y un pedido
de agregar un campo `priority` prohibiendo tocar el schema de Prisma
(el Implementer reconoció la contradicción y no forzó una implementación
rota).

## Criterio de éxito

Para este caso de uso (agregar funcionalidad real), una tarea se considera
resuelta cuando el `TaskState` final queda en `status: "done"` — lo que
implica, en cadena: el Tester corrió build/lint/test reales y pasaron, y el
Reviewer confirmó que los archivos modificados responden al pedido
original. Un `status: "blocked"` o `"needs_help"` no es
una falla del sistema: es el sistema reconociendo correctamente que no
pudo (o no debía) completar la tarea, y por qué — que es en sí mismo un
resultado válido y parte de lo que la consigna pide demostrar
(comportamiento seguro).
