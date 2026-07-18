# Reflexión

## Qué funcionó bien

**La separación de responsabilidades entre subagentes.** Darle a cada
subagente un set acotado de tools (Explorer y Reviewer sin escritura,
Tester solo con `run_command`, Implementer con todo) resultó en un sistema
mucho más fácil de razonar y de debuggear que un agente monolítico — cuando
algo salía mal, siempre quedaba claro en qué capa había pasado.

**La verificación en capas terminó siendo la parte más valiosa del
sistema**, no solo una formalidad de la consigna. En varias corridas reales
(documentadas en `docs/EVIDENCIA.md`), el Tester pasaba (los tests
existentes seguían en verde) pero el Reviewer igual rechazaba el trabajo
porque no cumplía el pedido completo (faltaban tests nuevos pedidos
explícitamente). Sin esa segunda capa de verificación "contra el pedido
original" en vez de "contra si algo rompió", el sistema hubiera reportado
`done` en tareas incompletas.

**Detectar loops y evidencia insuficiente resultó más sutil de lo que
parecía al principio.** No alcanza con "misma tool call repetida" — hicieron
falta varios mecanismos en capas distintas: repetición de tool calls dentro
de un subagente, el mismo error de Tester repitiéndose entre reintentos
(con un fingerprint que ignora ruido como duraciones), y el caso donde el
Implementer directamente decide no actuar por falta de evidencia (que sin
un chequeo explícito se colaba como un "éxito" trivial, porque el Tester no
tenía nada que romper). El caso más convincente fue orgánico, no forzado:
un bug real de tipado en el proyecto objetivo hizo que el sistema se
frenara solo y pidiera ayuda en vez de reintentar indefinidamente.

## Qué falló (y cómo se corrigió)

Durante el desarrollo aparecieron varios problemas reales, algunos
encontrados por accidente corriendo el sistema, otros por una revisión de
QA deliberada:

- El loop de function-calling de Explorer/Implementer podía agotar sus
  iteraciones sin nunca emitir una respuesta final parseable — se corrigió
  reservando la última iteración con `tool_choice="none"` forzado y
  repitiendo el schema exacto esperado.
- El Implementer tendía a "explicar un plan" en vez de aplicar los cambios
  — leía de más y nunca llamaba a `write_file`. Hizo falta instrucción
  explícita en el prompt más un forzado de `tool_choice` hacia `write_file`
  cuando se detectaba ese patrón.
- Un bug de lógica hacía que un comando de test que nunca había pasado
  (ej. `lint`) desapareciera silenciosamente del set de checks apenas otros
  comandos quedaban validados en memoria — el retry "pasaba" sin que el
  problema real se hubiera verificado de nuevo.
- Dos bugs de seguridad en las políticas de acceso: los patrones de
  bloqueo de paths (`.env`, `secrets/**`) solo protegían la raíz del
  workspace, no subcarpetas; y el deny-list de comandos peligrosos
  (`rm -rf`, `git push`) se podía evadir con un espacio doble, porque el
  comando se ejecuta igual (el shell colapsa espacios) pero la comparación
  de texto crudo no. Ambos se corrigieron normalizando antes de comparar.
- `write_file` no podía crear archivos en carpetas que todavía no
  existían — bloqueaba silenciosamente cualquier tarea que necesitara un
  módulo nuevo.

## Qué mejoraríamos

- **La base de conocimiento del RAG es chica** (3 documentos, 9 chunks).
  Alcanza para demostrar el mecanismo, pero para un caso de uso real
  convendría ampliarla — sobre todo cobertura de Jest, que hoy es el
  ecosistema con menos documentación propia.
- **Los clientes de embeddings y de Chroma se recrean en cada búsqueda RAG**
  en vez de reusarse — funciona, pero es una ineficiencia evitable.
- **El Implementer, en versiones tempranas del sistema, era más cauteloso
  de lo necesario**: en tareas que requerían crear estructura nueva (un
  módulo entero desde cero, no modificar algo existente) tendía a gastar
  iteraciones explorando en vez de escribir. El forzado de `tool_choice`
  hacia `write_file` a partir de cierta iteración (agregado después,
  primero de forma acotada y luego reforzado con umbrales dedicados de
  descubrimiento/acción) apunta directo a este problema — no volvimos a
  correr ese escenario puntual con la versión más reciente del Implementer
  para confirmar si quedó resuelto del todo.
- **`list_files` podría dar más señal por llamada.** Ya distingue carpetas
  de archivos (sufijo `/`), que era la confusión más común y costaba una
  llamada extra para resolverla. Lo que falta: tamaño de archivo, o una
  vista de árbol en vez de un listado plano por nivel, para que explorar un
  proyecto grande cueste menos iteraciones.
- Con más tiempo, generalizaríamos la detección de loops a nivel de
  subagente individual (hoy solo cubre tool-calls idénticos) para también
  reconocer variaciones menores de la misma tool call que no avanzan
  (ej. leer archivos distintos pero igual de irrelevantes, sin nueva
  información útil).
