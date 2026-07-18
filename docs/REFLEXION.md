# Reflexión

## Qué funcionó bien

La separación de responsabilidades entre subagentes fue una de las decisiones
más acertadas. Explorer, Researcher, Implementer, Tester y Reviewer tienen
objetivos y permisos diferentes, lo que hizo que el sistema fuera más fácil de
entender, auditar y depurar que un agente monolítico. Cuando una corrida falló,
fue posible identificar con claridad si el problema estaba en la exploración,
la investigación, la implementación, los checks o la revisión final.

También funcionó bien la verificación en capas. El Tester no se limita a correr
Jest: valida Prisma, lint, build y tests reales del repositorio. El Reviewer,
por su parte, no pregunta solamente si los checks pasaron, sino si el cambio
realmente coincide con el pedido original. Esta separación evita considerar
exitosa una implementación técnicamente válida pero incompleta.

Las corridas finales mostraron además que el ciclo
`Implementer → Tester → Implementer` puede recuperarse de errores reales. En
las tareas de ampliación de tests, el primer intento dejó fallos de lint por
tipado inseguro, uso de `any`, imports sin utilizar y formato. El Tester
devolvió esos errores como evidencia autoritativa, el Implementer corrigió el
código y el segundo Tester confirmó que Prisma, lint, build y Jest pasaban.

La combinación de repositorio, memoria y RAG también resultó útil. El Explorer
inspecciona archivos reales, la memoria conserva información validada de
corridas anteriores y el Researcher recupera únicamente los chunks técnicos
más relevantes. Esto permite reutilizar contexto sin reenviar el repositorio o
el historial completo en cada llamada.

## Qué falló y cómo se corrigió

Durante el desarrollo aparecieron problemas reales que obligaron a reforzar la
arquitectura.

En las primeras versiones, algunos subagentes podían agotar sus iteraciones sin
producir una salida estructurada. Se reservó la última iteración sin nuevas
tools y se volvió a indicar el schema esperado. Esto no garantiza que el
modelo siempre produzca JSON válido, pero reduce el problema y permite aplicar
un fallback que conserva el texto libre o marca la evidencia como insuficiente.

El Implementer también tendía a seguir explorando o a describir un plan sin
ejecutarlo. Para corregirlo se reforzó el prompt y se agregaron umbrales de
acción que pueden forzar `write_file` cuando el pedido requiere cambios y el
agente todavía no escribió nada. Además, cuando el pedido exige tests, se
controla que se haya modificado o creado un archivo de pruebas.

Otro problema apareció en la resolución de comandos del Tester. En una versión
anterior, si algunos comandos ya estaban validados en memoria, otro check que
nunca había pasado podía desaparecer del conjunto. Se corrigió combinando la
memoria y los scripts detectados por Explorer por clave, en lugar de tratar
ambas fuentes como alternativas excluyentes.

También se encontraron fallas de seguridad en la normalización de paths y
comandos. Los patrones protegidos debían bloquear archivos sensibles en
cualquier profundidad del workspace, y los comandos peligrosos debían
compararse después de normalizar espacios para impedir evasiones triviales.
Estas validaciones se centralizaron en `PolicyEngine` y `ToolExecutor`.

Por último, se mejoró `write_file` para crear directorios padres cuando fuera
necesario, ya que originalmente una tarea que requería un archivo dentro de una
carpeta nueva podía fallar antes de escribir.

## Cuándo se detectaron loops o falta de evidencia

El sistema distingue entre errores corregibles y situaciones en las que debe
detenerse.

Los errores de lint de las corridas finales fueron un ejemplo de progreso
posible: el Tester falló, el Implementer recibió feedback concreto, cambió la
implementación y el siguiente intento pasó. En este caso correspondía
reintentar.

Para evitar reintentos indefinidos, el Orchestrator genera un fingerprint de
los checks fallidos. Si dos intentos consecutivos presentan esencialmente el
mismo error, se considera que no hubo progreso y la tarea termina en
`needs_help`.

La falta de evidencia o de requisitos se observó con el pedido “Eliminar
automáticamente los tickets viejos”. El sistema pudo comprender el repositorio
y proponer alternativas técnicas, pero no tenía información suficiente para
decidir la antigüedad, la frecuencia, el tipo de borrado, las reglas de
retención, las cascadas o la auditoría. El Researcher devolvió
`requirements_clear: false` y el Orchestrator detuvo el flujo antes del
Implementer, sin modificar archivos. Este fue el ejemplo más claro de que
pedir ayuda puede ser el resultado correcto y seguro.

## Qué mejoraríamos

La base RAG sigue siendo deliberadamente pequeña. Actualmente cubre NestJS,
Prisma y Jest, pero para un uso real convendría incorporar más documentación
sobre testing e2e, errores HTTP, seguridad, migraciones y patrones de diseño.
También sería útil automatizar la revisión y actualización de las fuentes para
evitar documentación desactualizada.

El fallback web todavía puede mejorar. En una corrida se ejecutó la búsqueda
porque faltaba cobertura para ciertos ecosistemas, pero los resultados no
quedaron incorporados en `web_sources`. El sistema registró que el fallback se
ejecutó, pero convendría distinguir mejor entre “búsqueda realizada”,
“resultados recibidos” y “fuentes finalmente utilizadas”.

Otra mejora importante es el manejo de outputs estructurados. Aunque existen
schemas y fallbacks, todavía hubo respuestas de Explorer o Researcher que no
eran JSON válido. Una solución más robusta sería utilizar salidas estructuradas
estrictas del proveedor o una capa de validación y reparación centralizada.

El tracking de `files_modified` también puede refinarse. Actualmente combina
escrituras directas con cambios detectados mediante `git status`. Si el
workspace ya contiene modificaciones anteriores, pueden aparecer archivos que
no fueron escritos en la corrida actual. Para mejorar la atribución se podría
capturar un snapshot inicial de Git y comparar únicamente el delta de la
ejecución, o trabajar siempre sobre worktrees limpios y temporales.

Los clientes de embeddings y Chroma podrían reutilizarse en lugar de
recrearse en cada búsqueda. Esto reduciría latencia y simplificaría el manejo
de recursos.

Finalmente, `list_files` podría devolver más señal por llamada, por ejemplo una
vista de árbol, tamaño de archivos y límites configurables de profundidad.
Esto reduciría iteraciones de exploración en repositorios grandes. También se
podría ampliar la detección de loops para reconocer secuencias distintas de
tools que, aunque no sean idénticas, siguen sin aportar información nueva.

## Conclusión

El aprendizaje principal fue que un coding agent confiable no depende solo de
generar buen código. Necesita separar responsabilidades, controlar permisos,
mantener evidencia, validar con herramientas reales, revisar el pedido
original, limitar los reintentos y reconocer cuándo no debe avanzar.

Las fallas encontradas durante el desarrollo fueron útiles porque obligaron a
convertir supuestos implícitos en controles concretos. El resultado final no
elimina todos los riesgos, pero ofrece un pipeline trazable, supervisado y
capaz de corregirse o detenerse de manera explícita.