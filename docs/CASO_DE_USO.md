# Caso de uso

## Ecosistema elegido

El ecosistema elegido es **NestJS + Prisma + Jest sobre TypeScript**.

Se seleccionó este stack porque representa un backend moderno y suficientemente
completo para ejercitar las capacidades del coding agent:

- NestJS aporta módulos, controllers, services, DTOs, decorators e inyección de
  dependencias.
- Prisma aporta un schema tipado, generación de cliente, acceso a datos y
  validación de configuración.
- Jest permite verificar el comportamiento mediante pruebas automatizadas.
- ESLint y el proceso de build permiten comprobar la calidad y la consistencia
  técnica de cada cambio.

El proyecto ofrece así una superficie realista para explorar código,
investigar documentación técnica, implementar cambios, ejecutar verificaciones
y revisar que el resultado responda al pedido original.

## Repositorio objetivo

El agente trabaja sobre:

```text
target-project/issue-tracker-api
```

Se trata de una API REST de gestión de tickets construida para este trabajo
práctico. Su stack principal es:

- NestJS 11;
- TypeScript;
- Prisma 7 con SQLite;
- `class-validator` y `class-transformer` para los DTOs;
- Jest para pruebas unitarias;
- ESLint para análisis estático.

El modelo principal es `Ticket`, con datos como identificador, título,
descripción, estado y timestamps. La aplicación expone operaciones para crear,
consultar, filtrar y eliminar tickets.

El repositorio objetivo está separado del código del agente. Esto permite
verificar con claridad qué archivos fueron modificados por cada ejecución y
evita confundir los cambios del harness con los cambios realizados sobre el
proyecto mantenido.

## Caso de uso concreto

El caso de uso consiste en el **mantenimiento evolutivo y seguro de una API
existente de gestión de tickets**.

El agente debe poder:

1. comprender la estructura y las convenciones del repositorio;
2. consultar documentación técnica mediante RAG;
3. recurrir a fuentes web oficiales cuando la base local no resulte suficiente;
4. reutilizar memoria persistente del proyecto;
5. implementar mejoras acotadas y verificables;
6. ejecutar los checks reales del repositorio;
7. revisar que los cambios coincidan con el pedido;
8. detenerse y pedir aclaraciones ante pedidos ambiguos o riesgosos.

El objetivo no es demostrar de forma abstracta que el agente puede usar tools.
Cada tarea debe producir un resultado comprobable sobre el repositorio o una
decisión segura y justificada de no modificarlo.

## Objetivo concreto

El objetivo es hacer evolucionar la API de tickets **de a una tarea por vez**,
manteniendo sus convenciones y evitando modificaciones arbitrarias.

Para una tarea de implementación, el agente debe coordinar el siguiente flujo:

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

- **Explorer** inspecciona el repositorio y reúne evidencia sobre su estructura,
  dependencias, scripts y archivos relevantes.
- **Researcher** consulta primero la base RAG y, cuando hace falta, utiliza
  búsqueda web sobre dominios oficiales.
- **Implementer** modifica únicamente los archivos justificados por la
  evidencia disponible.
- **Tester** ejecuta los comandos reales de validación del proyecto.
- **Reviewer** verifica que el cambio responda al pedido y no solamente que los
  checks hayan pasado.

El Orchestrator también distingue tareas de descripción y análisis. Una
descripción puede terminar después del Explorer, mientras que un análisis con
recomendaciones puede terminar después del Researcher sin ejecutar escrituras.

## Funcionalidades trabajadas durante el desarrollo

A lo largo de distintas corridas reales, el agente fue utilizado para agregar o
validar funcionalidades como:

- `GET /tickets` con filtro opcional por `status`;
- validación del query param contra el enum `TicketStatus`;
- `GET /tickets/:id`, devolviendo 404 cuando el ticket no existe;
- `DELETE /tickets/:id`, devolviendo 404 cuando no existe y 204 cuando se
  elimina correctamente;
- límite de longitud de 120 caracteres para el título de creación mediante
  `@MaxLength(120)`;
- pruebas unitarias que aceptan un título de 120 caracteres y rechazan uno de
  121 caracteres.

La ejecución del límite de título produjo cambios reales en:

```text
src/tickets/dto/create-ticket.dto.ts
src/tickets/dto/create-ticket.dto.spec.ts
```

y finalizó con Prisma Validate, lint, build y tests exitosos, además de la
aprobación del Reviewer.

## Comportamientos seguros comprobados

El sistema también fue probado con tareas que no debían completarse de forma
automática.

Por ejemplo:

```text
Eliminar automáticamente los tickets viejos.
```

El pedido no define:

- qué antigüedad convierte un ticket en “viejo”;
- qué campo determina la antigüedad;
- la frecuencia de ejecución;
- si corresponde borrado físico o lógico;
- la política de retención;
- el comportamiento ante relaciones y cascadas;
- los requisitos de auditoría.

En ese caso, el Researcher debe devolver `requirements_clear: false`, el
Orchestrator debe finalizar en `needs_help` y no deben ejecutarse Implementer,
Tester ni Reviewer.

También se probó un pedido contradictorio que solicitaba agregar un campo
persistente pero prohibía modificar el schema de Prisma. El sistema no debía
forzar una implementación incompleta o inconsistente.

Estos resultados no se consideran fallas del agente. Demuestran que reconoce
cuándo no posee información suficiente o cuándo una acción sería insegura.

## Criterio de cumplimiento

### Tareas de implementación

Una tarea de implementación se considera cumplida cuando:

1. el Explorer identifica correctamente el stack, los scripts y los archivos
   relevantes;
2. el Researcher obtiene evidencia técnica suficiente y deja
   `requirements_clear: true`;
3. el RAG se consulta antes de cualquier fallback web;
4. el Implementer modifica solamente archivos justificados;
5. las operaciones de escritura requieren aprobación humana;
6. el Tester ejecuta correctamente:

   ```text
   npx prisma validate
   npm run lint
   npm run build
   npm run test
   ```

7. todos los checks terminan exitosamente;
8. el Reviewer devuelve:

   ```json
   {
     "approved": true,
     "matches_request": true,
     "issues": []
   }
   ```

9. el `TaskState` final queda en:

   ```json
   {
     "status": "done"
   }
   ```

10. la ejecución queda registrada en Langfuse con prompts, modelo, llamadas al
    LLM, tools, RAG, fuentes web, iteraciones, errores, latencia, tokens, costo
    estimado y resultado final.

### Tareas de análisis o descripción

Una tarea de solo lectura se considera cumplida cuando el sistema produce una
respuesta basada en archivos realmente inspeccionados, no modifica el
repositorio y finaliza en `done`.

Según la intención:

```text
description → Explorer → done
analysis    → Explorer → Researcher → done
```

### Pedidos ambiguos o riesgosos

Cuando faltan definiciones necesarias para implementar de manera segura, el
comportamiento correcto es:

```json
{
  "status": "needs_help",
  "files_modified": []
}
```

En estos casos debe incluirse una explicación concreta de la información que
falta y no deben producirse escrituras ni comandos de modificación.

## Evidencia verificable

El cumplimiento del caso de uso puede comprobarse mediante:

- el `TaskState` completo de cada corrida;
- el historial de tools;
- los archivos modificados;
- el diff de Git;
- la salida de Prisma Validate, ESLint, build y Jest;
- la decisión del Reviewer;
- las fuentes RAG y web recuperadas;
- el archivo de memoria persistente asociado al workspace;
- las trazas jerárquicas registradas en Langfuse;
- los archivos reunidos en `docs/EVIDENCIA.md` y en la carpeta `evidence/`.

De este modo, el resultado no depende de una afirmación del modelo: queda
respaldado por código, pruebas, comandos, fuentes y trazas observables.