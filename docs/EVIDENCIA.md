# Evidencia de tareas ejecutadas

Todas las corridas listadas acá son reales: LLM real, RAG real, comandos
reales (`npx prisma validate`, `npm run build/lint/test`) corridos contra
`target-project/issue-tracker-api`. Los JSON completos de las primeras 6
están en `evidence/smoke/`.

## 1. Pedido ambiguo → `needs_help` (`evidence/smoke/01-needs-help.txt`)

**Pedido:** *"Eliminar automáticamente los tickets viejos."*

**Resultado:** `needs_help`, `files_modified: []`.

**Qué se observa:** el Researcher determinó que al pedido le faltan
definiciones funcionales básicas (¿qué es "viejo"? ¿hay una política de
retención? ¿debe ser un cron, un endpoint manual?) y lo marcó como
`requirements_clear: false`. El Orchestrator cortó **antes** de llegar al
Implementer — no se intentó adivinar una implementación. Es exactamente el
comportamiento que pide la consigna: reconocer cuándo falta evidencia y
explicar qué falta, en vez de alucinar una solución.

## 2 y 3. Mismo pedido, dos intentos bloqueados por falta de tests

**Pedido:** *"Agregar una validación para que el título de un ticket tenga
como máximo 120 caracteres, manteniendo la validación mínima existente, y
agregar tests unitarios para este caso."*

- `02-full-pipeline2.txt` → `status: blocked`. Se modificó
  `create-ticket.dto.ts` (el `MaxLength(120)` se agregó correctamente), pero
  **no** se agregaron tests. El Reviewer lo detectó explícitamente:
  *"no se añadieron las pruebas [...] solicitadas"* → `approved: false`.
- `02-full-pipeline3.txt` → mismo resultado, mismo motivo de rechazo.

**Qué se observa:** el Tester había pasado (los tests *existentes* seguían
pasando), pero eso no alcanzó para engañar al Reviewer — que compara contra
el pedido original, no solo contra "¿rompió algo?". Es la red de seguridad
Implementer↔Tester↔Reviewer funcionando en capas: pasar los checks
automáticos no es lo mismo que cumplir el pedido.

## 4. Mismo pedido, tercer intento → `done` (`02-full-pipeline4.txt`)

**Resultado:** `status: done`. `files_modified` incluye ahora
`create-ticket.dto.ts` **y** `create-ticket.dto.spec.ts` (tests nuevos).
Reviewer: *"Pruebas unitarias añadidas [...] verificando título a ≤ 120
caracteres y > 120 [...]"* → `approved: true`.

**Qué se observa:** sobre el mismo pedido, cuando el Implementer sí
completa lo pedido (incluidos los tests), el pipeline completo — Tester y
Reviewer — lo confirma y cierra la tarea como exitosa. Las tres corridas
(2, 3, 4) juntas muestran el mismo mecanismo de verificación funcionando de
forma consistente, no solo una vez de casualidad.

## 5. Modo descripción (`03-description-only.txt`)

**Pedido:** *"Explicame cómo está implementada la creación de tickets."*

**Resultado:** `done`, corre **solo** el Explorer (10 iteraciones, 5
archivos leídos), sin Researcher/Implementer/Tester/Reviewer.

**Qué se observa:** `request_mode.py` clasificó correctamente el pedido
como `DESCRIPTION` y el Orchestrator ajustó el pipeline en consecuencia —
no tiene sentido correr Tester/Reviewer sobre una pregunta que no modifica
nada.

## 6. Modo análisis de solo lectura (`04-read-only-analysis.txt`)

**Pedido:** *"Analizar cómo está implementada actualmente la creación de
tickets y señalar posibles mejoras, sin modificar archivos."*

**Resultado:** `done`, corre Explorer + Researcher, termina sin pasar por
Implementer.

**Qué se observa:** la restricción explícita de "sin modificar archivos" se
clasificó como `ANALYSIS`, y el Orchestrator respetó esa restricción
estructuralmente (ni siquiera instanció el Implementer), no solo
confiando en que el modelo "decida" no escribir nada.

## Nota sobre procedencia

Los ítems 1 a 6 están respaldados por los JSON completos en
`evidence/smoke/`, verificados campo por campo contra este documento. Los
ítems 7 a 9 documentan corridas reales hechas durante el desarrollo (con
versiones del código previas a la última reescritura de `orchestrator.py`
y `subagents/researcher.py`), cuyos JSON completos no quedaron persistidos
como archivo en el repo. El mecanismo que describen sigue vigente hoy,
aunque el texto exacto de algunos mensajes de log haya cambiado desde
entonces (se aclara en el ítem 9). Quedan documentados igual porque
ilustran comportamientos (fuentes RAG, memoria reutilizada, loop
detenido) que no aparecen tan explícitamente en los `evidence/smoke/`
actuales.

## 7. Fuentes RAG mostradas explícitamente

En corridas sobre pedidos relacionados a filtrado por `status` (enum de
Prisma) y validación de DTOs, el Researcher devolvió evidencia trazable del
RAG, por ejemplo:

```json
"rag_sources": [
  {"chunk_id": "87eab706022adc7a7cf7d0e3", "source": "prisma/filtering.md",
   "section": "Enums", "similarity": 0.5115},
  {"chunk_id": "e328fdf8ae7b93f8f179de90", "source": "nestjs/validation.md",
   "section": "DTOs de query", "similarity": 0.4622}
],
"web_sources": [],
"used_web_fallback": false
```

**Qué se observa:** el RAG tuvo evidencia suficiente (`similarity` por
encima del umbral configurado) y **no** necesitó fallback web — la
recomendación final del Researcher cita directamente esos `chunk_id` como
evidencia. En otras corridas donde el RAG no tuvo cobertura suficiente para
el pedido (ej. un endpoint `DELETE`, tema no cubierto en la base de
conocimiento actual), el sistema activó el fallback web automáticamente y
lo dejó registrado en `used_web_fallback: true` con las URLs reales
devueltas por Tavily.

