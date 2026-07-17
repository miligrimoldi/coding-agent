import json
from pathlib import Path
from typing import Optional, Set

from llm_client import get_client, MODEL
from task_state import TaskState, SubagentResult
from tool_executor import ToolExecutor
from tools.loader import get_tools_for


ALLOWED_TOOLS = [
    "read_file",
    "write_file",
    "list_files",
    "run_command",
]

IMPLEMENTER_TOOLS = get_tools_for(ALLOWED_TOOLS)


class Implementer:
    MAX_ITERATIONS = 12
    REPEAT_THRESHOLD = 2

    # Si ya leyó suficiente y todavía no escribió, fuerza el primer cambio.
    ACTION_ITERATION = 8

    # Si la tarea pide tests y ya modificó código productivo, fuerza la
    # escritura del archivo de tests antes de terminar.
    TEST_COMPLETION_ITERATION = 10

    # Evita que el Implementer consuama todas las iteraciones explorando.
    MAX_DISCOVERY_CALLS_BEFORE_WRITE = 6

    TEST_FILE_SUFFIXES = (
        ".spec.ts",
        ".test.ts",
        ".spec.js",
        ".test.js",
        ".spec.tsx",
        ".test.tsx",
    )

    SYSTEM_PROMPT = """
Sos el subagente Implementer dentro de un sistema multiagente de desarrollo
de código.

Tu responsabilidad es modificar el código real del repositorio para resolver
completamente el pedido del usuario, a partir de la evidencia reunida por el
Explorer y el Researcher.

Recibís, en el primer mensaje, un JSON con:
- pedido_original: el pedido del usuario;
- hallazgos_explorer: estructura, archivos relevantes y convenciones
  detectadas;
- hallazgos_researcher: recomendaciones técnicas, claridad de los requisitos
  y fuentes consultadas;
- resultado_tester_previo: si no es null, significa que ya intentaste esta
  misma tarea antes y el Tester encontró uno o más errores. Usá esos errores
  para corregir el problema puntual y no repitas el mismo cambio;
- memoria_previa_del_proyecto: puede ser null. Si no lo es, contiene
  decisiones, convenciones, comandos y bugs de corridas anteriores sobre
  este mismo repositorio.

Reglas:
- Usá read_file para ver el contenido actual de un archivo antes de
  modificarlo.
- write_file reemplaza el contenido completo del archivo. Para modificar un
  archivo existente, primero leelo, después generá su contenido completo
  modificado y recién entonces escribilo.
- Para crear un archivo nuevo, como un nuevo archivo de tests, primero
  confirmá el directorio y sus convenciones mediante list_files y/o leyendo
  archivos similares. No intentes leer repetidamente un archivo que todavía
  no existe.
- No inventes APIs, decorators, comandos ni convenciones que no estén
  respaldadas por los hallazgos del Explorer o del Researcher.
- No modifiques archivos que no hayan sido identificados como relevantes o
  cuya modificación no puedas justificar con la evidencia disponible.
- Usá exclusivamente paths confirmados por Explorer, list_files o read_file.
  No inventes variantes de paths.
- No repitas la misma lectura, escritura o listado si ya obtuviste esa
  información.
- Si hallazgos_researcher indica requirements_clear=false, no escribas
  código. Explicá qué aclaraciones funcionales necesita el usuario.
- Si el pedido es ambiguo o no hay evidencia suficiente para decidir con
  confianza, no escribas código al azar. Respondé con evidence_sufficient
  en false, changes vacío y explicá en risks_or_notes qué falta.
- Cuando hallazgos_researcher indique evidence_sufficient=true y
  requirements_clear=true, y ya hayas leído los archivos directamente
  involucrados, aplicá el cambio. No sigas explorando archivos secundarios.
- Para tareas pequeñas y localizadas, no uses más de seis llamadas de
  lectura o listado antes del primer write_file.
- Priorizá actuar. Un plan de lo que harías, sin haber llamado a write_file,
  no es una implementación válida.
- Si el pedido exige tests, la tarea no está completa hasta que hayas creado
  o modificado un archivo .spec o .test que compruebe explícitamente el
  comportamiento solicitado.
- No respondas con el JSON final después de modificar solamente el código
  productivo cuando el pedido también exige tests.
- No afirmes que faltan herramientas cuando write_file o run_command están
  disponibles. Si decidís no actuar, explicá la incertidumbre concreta.
- En pedidos destructivos con términos indefinidos como "viejos",
  "automáticamente" o "eliminar", no elijas valores arbitrarios.
- Usá run_command solamente cuando sea necesario para completar la
  implementación, por ejemplo para generar un cliente o una migración.
- No ejecutes los checks generales de build, lint o test. Esa responsabilidad
  pertenece al Tester.
- No ejecutes comandos que no estén respaldados por la evidencia del
  repositorio.
- Cuando termines, respondé con un único objeto JSON, sin texto alrededor,
  con esta forma:
  {
    "evidence_sufficient": true,
    "summary": "resumen breve de qué se implementó",
    "changes": [
      {
        "file": "...",
        "reason": "..."
      }
    ],
    "risks_or_notes": ["..."]
  }
"""

    ACTION_REMINDER = """
AVISO DEL SISTEMA: el Researcher confirmó que existe evidencia técnica
suficiente y que los requisitos son claros.

Ya inspeccionaste archivos relevantes y todavía no aplicaste ninguna
escritura. No sigas leyendo archivos secundarios ni describas solamente un
plan.

En esta iteración debés usar write_file para aplicar el primer cambio real.
El contenido enviado a write_file debe representar el archivo completo y
debe conservar todo lo que no corresponda modificar.
"""

    TESTS_REQUIRED_REMINDER = """
AVISO DEL SISTEMA: el pedido original exige agregar o actualizar tests, pero
durante esta ejecución todavía no modificaste ningún archivo de test.

Ya aplicaste al menos un cambio de implementación. Ahora debés usar
write_file para crear o actualizar un archivo .spec o .test que compruebe
explícitamente el comportamiento solicitado.

No vuelvas a modificar solamente el archivo productivo y no respondas con
el JSON final hasta haber aplicado los tests requeridos.

Si vas a crear un archivo nuevo, usá un path coherente con la estructura que
ya inspeccionaste y escribí el contenido completo del nuevo archivo.
"""

    FINAL_ITERATION_REMINDER = """
AVISO DEL SISTEMA: esta es la última iteración disponible. Ya no podés usar
tools ni llamar a write_file.

Respondé ahora ÚNICAMENTE con un objeto JSON, sin texto antes ni después:

{
  "evidence_sufficient": true,
  "summary": "resumen breve de qué se implementó",
  "changes": [
    {
      "file": "...",
      "reason": "..."
    }
  ],
  "risks_or_notes": ["..."]
}

Informá solamente cambios que hayan sido escritos realmente.

Si no aplicaste ninguna escritura real, marcá evidence_sufficient en false,
dejá changes vacío y explicá que no se aplicaron cambios.

Si el pedido exigía tests y no llegaste a escribir ningún archivo de test,
marcá evidence_sufficient en false e indicá que la implementación quedó
incompleta.
"""

    def __init__(
        self,
        tool_executor: ToolExecutor,
    ):
        self.tool_executor = tool_executor

    def run(
        self,
        task_state: TaskState,
    ) -> SubagentResult:
        client = get_client()
        task_state.set_phase("implementation")

        explorer_result = task_state.last_result_of("explorer")

        if explorer_result is None:
            task_state.status = "needs_help"

            return SubagentResult(
                subagent="implementer",
                summary=(
                    "No se pudo implementar porque falta "
                    "el resultado del Explorer."
                ),
                data={
                    "evidence_sufficient": False,
                    "reason": "missing_explorer_result",
                    "summary": "",
                    "changes": [],
                    "risks_or_notes": [
                        "No existe evidencia del repositorio."
                    ],
                },
                sources=[],
            )

        researcher_result = task_state.last_result_of(
            "researcher"
        )
        tester_result = task_state.last_result_of(
            "tester"
        )

        researcher_data = (
            researcher_result.data
            if researcher_result
            else {}
        )

        evidence_sufficient = (
            researcher_data.get("evidence_sufficient")
            is True
        )

        requirements_clear = (
            researcher_data.get(
                "requirements_clear",
                True,
            )
            is True
        )

        safe_to_implement = (
            evidence_sufficient
            and requirements_clear
        )

        request_lower = (
            task_state.original_request.lower()
        )

        tests_required = any(
            term in request_lower
            for term in (
                "test",
                "tests",
                "prueba",
                "pruebas",
                "spec",
                "e2e",
            )
        )

        memory = task_state.project_memory

        used_memory = bool(
            memory
            and memory.has_prior_knowledge()
        )

        context = {
            "pedido_original": (
                task_state.original_request
            ),
            "hallazgos_explorer": (
                explorer_result.data
            ),
            "hallazgos_researcher": (
                researcher_data
                if researcher_result
                else None
            ),
            "resultado_tester_previo": (
                tester_result.data
                if tester_result
                else None
            ),
            "memoria_previa_del_proyecto": (
                memory.as_context()
                if used_memory
                else None
            ),
            "tests_requeridos": tests_required,
        }

        messages = [
            {
                "role": "system",
                "content": self.SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": json.dumps(
                    context,
                    ensure_ascii=False,
                ),
            },
        ]

        successful_reads = 0
        discovery_calls = 0

        # Registra solamente las escrituras realizadas durante esta
        # ejecución particular del Implementer.
        written_files_this_run: Set[str] = set()

        action_reminder_sent = False
        tests_reminder_sent = False

        for iteration in range(
            1,
            self.MAX_ITERATIONS + 1,
        ):
            is_last_iteration = (
                iteration == self.MAX_ITERATIONS
            )

            test_file_written = self._has_test_file(
                written_files_this_run
            )

            exceeded_discovery_limit = (
                discovery_calls
                >= self.MAX_DISCOVERY_CALLS_BEFORE_WRITE
            )

            reached_action_iteration = (
                iteration >= self.ACTION_ITERATION
            )

            must_write_now = bool(
                not is_last_iteration
                and safe_to_implement
                and successful_reads >= 2
                and not written_files_this_run
                and (
                    exceeded_discovery_limit
                    or reached_action_iteration
                )
            )

            must_write_tests_now = bool(
                not is_last_iteration
                and safe_to_implement
                and tests_required
                and bool(written_files_this_run)
                and not test_file_written
                and (
                    iteration
                    >= self.TEST_COMPLETION_ITERATION
                )
            )

            if (
                must_write_now
                and not action_reminder_sent
            ):
                messages.append({
                    "role": "user",
                    "content": self.ACTION_REMINDER,
                })

                action_reminder_sent = True

            if (
                must_write_tests_now
                and not tests_reminder_sent
            ):
                messages.append({
                    "role": "user",
                    "content": (
                        self.TESTS_REQUIRED_REMINDER
                    ),
                })

                tests_reminder_sent = True

            if is_last_iteration:
                messages.append({
                    "role": "user",
                    "content": (
                        self.FINAL_ITERATION_REMINDER
                    ),
                })

            if is_last_iteration:
                tool_choice = "none"

            elif must_write_tests_now:
                tool_choice = {
                    "type": "function",
                    "function": {
                        "name": "write_file",
                    },
                }

            elif must_write_now:
                tool_choice = {
                    "type": "function",
                    "function": {
                        "name": "write_file",
                    },
                }

            else:
                tool_choice = "auto"

            response = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                tools=IMPLEMENTER_TOOLS,
                tool_choice=tool_choice,
            )

            assistant_message = (
                response.choices[0].message
            )

            if not assistant_message.tool_calls:
                test_file_written = (
                    self._has_test_file(
                        written_files_this_run
                    )
                )

                missing_required_tests = bool(
                    safe_to_implement
                    and tests_required
                    and bool(written_files_this_run)
                    and not test_file_written
                )

                # No permite que el modelo termine después de escribir
                # solamente el código productivo cuando también se
                # solicitaron tests.
                if (
                    missing_required_tests
                    and not is_last_iteration
                ):
                    messages.append(
                        assistant_message
                    )

                    if not tests_reminder_sent:
                        messages.append({
                            "role": "user",
                            "content": (
                                self.TESTS_REQUIRED_REMINDER
                            ),
                        })

                        tests_reminder_sent = True

                    else:
                        messages.append({
                            "role": "user",
                            "content": (
                                "Todavía faltan los tests "
                                "solicitados. Usá write_file "
                                "para agregarlos antes de "
                                "finalizar."
                            ),
                        })

                    continue

                task_state.record_iterations(
                    "implementer",
                    iteration,
                )

                return self._finalize(
                    task_state=task_state,
                    content=assistant_message.content,
                    iterations=iteration,
                    used_memory=used_memory,
                    written_files_this_run=(
                        written_files_this_run
                    ),
                    safe_to_implement=(
                        safe_to_implement
                    ),
                    tests_required=tests_required,
                )

            messages.append(
                assistant_message
            )

            for tool_call in (
                assistant_message.tool_calls
            ):
                tool_name = (
                    tool_call.function.name
                )

                try:
                    tool_args = json.loads(
                        tool_call.function.arguments
                        or "{}"
                    )

                except json.JSONDecodeError as exc:
                    tool_result = (
                        "Error: los argumentos de la "
                        "tool no son JSON válido: "
                        f"{exc}"
                    )

                    task_state.record_observation(
                        tool_result
                    )

                    messages.append({
                        "role": "tool",
                        "tool_call_id": (
                            tool_call.id
                        ),
                        "content": tool_result,
                    })

                    continue

                if task_state.is_repeating(
                    subagent="implementer",
                    tool_name=tool_name,
                    args=tool_args,
                    threshold=self.REPEAT_THRESHOLD,
                ):
                    task_state.record_tool_call(
                        subagent="implementer",
                        tool_name=tool_name,
                        args=tool_args,
                        outcome="blocked_repeat",
                    )

                    task_state.record_observation(
                        "Implementer repitió "
                        f"{tool_name}({tool_args})."
                    )

                    tool_result = (
                        "AVISO DEL SISTEMA: esta misma "
                        "tool call ya fue ejecutada dos "
                        "veces. No la repitas. Usá otra "
                        "estrategia o entregá el JSON "
                        "final."
                    )

                else:
                    tool_result = (
                        self.tool_executor.execute(
                            subagent="implementer",
                            tool_name=tool_name,
                            arguments=tool_args,
                            task_state=task_state,
                            allowed_tools=ALLOWED_TOOLS,
                        )
                    )

                tool_result_text = str(tool_result)

                tool_failed = (
                    tool_result_text.startswith("Error")
                    or tool_result_text.startswith(
                        "POLICY_BLOCKED"
                    )
                    or tool_result_text.startswith(
                        "TOOL_EXECUTION_ERROR"
                    )
                    or tool_result_text.startswith(
                        "Ejecución de"
                    )
                    or tool_result_text.startswith(
                        "AVISO DEL SISTEMA"
                    )
                )

                if (
                    not tool_failed
                    and tool_name
                    in {"read_file", "list_files"}
                ):
                    discovery_calls += 1

                if (
                    not tool_failed
                    and tool_name == "read_file"
                ):
                    successful_reads += 1

                write_succeeded = bool(
                    tool_name == "write_file"
                    and tool_result_text.startswith(
                        "Successfully wrote file:"
                    )
                )

                if write_succeeded:
                    written_path = (
                        self._normalize_written_path(
                            path_value=tool_args.get(
                                "path",
                                "",
                            ),
                            workspace_path=(
                                task_state.workspace_path
                            ),
                        )
                    )

                    if written_path:
                        written_files_this_run.add(
                            written_path
                        )

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": tool_result_text,
                })

        task_state.record_iterations(
            "implementer",
            self.MAX_ITERATIONS,
        )

        task_state.record_observation(
            "Implementer alcanzó el límite de "
            f"{self.MAX_ITERATIONS} iteraciones."
        )

        return self._finalize(
            task_state=task_state,
            content=json.dumps(
                {
                    "evidence_sufficient": False,
                    "summary": (
                        "El Implementer alcanzó el límite "
                        "de iteraciones."
                    ),
                    "changes": [],
                    "risks_or_notes": [
                        "Se alcanzó el límite de "
                        "iteraciones antes de completar "
                        "la tarea."
                    ],
                },
                ensure_ascii=False,
            ),
            iterations=self.MAX_ITERATIONS,
            used_memory=used_memory,
            written_files_this_run=(
                written_files_this_run
            ),
            safe_to_implement=safe_to_implement,
            tests_required=tests_required,
        )

    @classmethod
    def _has_test_file(
        cls,
        paths: Set[str],
    ) -> bool:
        return any(
            cls._is_test_file(path)
            for path in paths
        )

    @classmethod
    def _is_test_file(
        cls,
        path: str,
    ) -> bool:
        normalized = (
            str(path)
            .replace("\\", "/")
            .lower()
        )

        filename = normalized.rsplit("/", 1)[-1]

        return bool(
            filename.endswith(
                cls.TEST_FILE_SUFFIXES
            )
            or normalized.startswith("test/")
            or "/test/" in f"/{normalized}"
            or normalized.startswith("tests/")
            or "/tests/" in f"/{normalized}"
        )

    @staticmethod
    def _normalize_written_path(
        *,
        path_value: str,
        workspace_path: str,
    ) -> str:
        """
        Convierte el path utilizado en write_file a un path relativo al
        workspace para mostrarlo y compararlo de forma consistente.
        """

        if (
            not isinstance(path_value, str)
            or not path_value.strip()
        ):
            return ""

        try:
            workspace = Path(
                workspace_path
            ).resolve()

            candidate = Path(
                path_value
            )

            if candidate.is_absolute():
                return (
                    candidate
                    .resolve()
                    .relative_to(workspace)
                    .as_posix()
                )

            return candidate.as_posix()

        except (OSError, ValueError):
            return str(path_value)

    @classmethod
    def _finalize(
        cls,
        *,
        task_state: TaskState,
        content: Optional[str],
        iterations: int,
        used_memory: bool,
        written_files_this_run: Set[str],
        safe_to_implement: bool,
        tests_required: bool,
    ) -> SubagentResult:
        try:
            data = json.loads(content or "")

        except (
            json.JSONDecodeError,
            TypeError,
        ):
            task_state.record_observation(
                "Implementer no devolvió JSON "
                "válido; se guardó como texto libre."
            )

            data = {
                "evidence_sufficient": False,
                "summary": "",
                "changes": [],
                "risks_or_notes": [],
                "resumen_libre": content,
            }

        if not isinstance(data, dict):
            data = {
                "evidence_sufficient": False,
                "summary": "",
                "changes": [],
                "risks_or_notes": [
                    "La respuesta final del "
                    "Implementer no tenía el "
                    "formato esperado."
                ],
            }

        actual_modified_files = set(
            written_files_this_run
        )

        test_file_written = cls._has_test_file(
            actual_modified_files
        )

        notes = data.get(
            "risks_or_notes",
            [],
        )

        if not isinstance(notes, list):
            notes = []

        changes = data.get(
            "changes",
            [],
        )

        if not isinstance(changes, list):
            changes = []

        # Asegura que todos los archivos realmente escritos aparezcan
        # también en la declaración de cambios.
        declared_files = {
            change.get("file")
            for change in changes
            if isinstance(change, dict)
            and isinstance(
                change.get("file"),
                str,
            )
        }

        for path in sorted(actual_modified_files):
            if path not in declared_files:
                changes.append({
                    "file": path,
                    "reason": (
                        "Archivo modificado realmente "
                        "durante la ejecución del "
                        "Implementer."
                    ),
                })

        data["changes"] = changes

        if not actual_modified_files:
            data["evidence_sufficient"] = False
            data["changes"] = []

            no_write_note = (
                "No se registraron escrituras reales "
                "durante esta ejecución del "
                "Implementer."
            )

            if no_write_note not in notes:
                notes.append(no_write_note)

        elif not safe_to_implement:
            data["evidence_sufficient"] = False

            unsafe_note = (
                "Se registraron escrituras, pero el "
                "Researcher no había confirmado al "
                "mismo tiempo evidencia suficiente y "
                "requisitos claros."
            )

            if unsafe_note not in notes:
                notes.append(unsafe_note)

        elif tests_required and not test_file_written:
            data["evidence_sufficient"] = False

            missing_tests_note = (
                "La implementación quedó incompleta "
                "porque el pedido exigía tests y no se "
                "modificó ningún archivo de test."
            )

            if missing_tests_note not in notes:
                notes.append(
                    missing_tests_note
                )

            data["summary"] = (
                "Se aplicaron cambios parciales en "
                + ", ".join(
                    sorted(actual_modified_files)
                )
                + ", pero faltaron los tests "
                "solicitados."
            )

        else:
            # La evidencia era suficiente y todos los cambios requeridos
            # fueron escritos realmente.
            data["evidence_sufficient"] = True

            summary = data.get(
                "summary",
                "",
            )

            invalid_summary = bool(
                not isinstance(summary, str)
                or not summary.strip()
                or "no se pudieron aplicar"
                in summary.lower()
                or "no se realizaron cambios"
                in summary.lower()
                or "no se pueden usar herramientas"
                in summary.lower()
                or "alcanzó el límite"
                in summary.lower()
            )

            if invalid_summary:
                data["summary"] = (
                    "Se aplicaron cambios reales en "
                    + ", ".join(
                        sorted(actual_modified_files)
                    )
                    + "."
                )

        data["risks_or_notes"] = notes

        sources = (
            ["repository", "memory"]
            if used_memory
            else ["repository"]
        )

        return SubagentResult(
            subagent="implementer",
            summary=(
                "Implementación completada en "
                f"{iterations} iteraciones "
                f"({len(actual_modified_files)} "
                "archivo(s) modificado(s) "
                "realmente durante esta llamada)."
            ),
            data=data,
            sources=sources,
        )