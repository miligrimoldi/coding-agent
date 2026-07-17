import json

from llm_client import get_client, MODEL
from task_state import TaskState, SubagentResult
from tool_executor import ToolExecutor
from tools.loader import get_tools_for


ALLOWED_TOOLS = ["read_file", "write_file", "list_files", "run_command"]
IMPLEMENTER_TOOLS = get_tools_for(ALLOWED_TOOLS)


class Implementer:
    MAX_ITERATIONS = 12
    REPEAT_THRESHOLD = 2

    SYSTEM_PROMPT = """
Sos el subagente Implementer dentro de un sistema multiagente de desarrollo
de código.

Tu responsabilidad es modificar el código real del repositorio para resolver
el pedido del usuario, a partir de la evidencia reunida por el Explorer y el
Researcher.

Recibís, en el primer mensaje, un JSON con:
- pedido_original: el pedido del usuario;
- hallazgos_explorer: estructura, archivos relevantes y convenciones detectadas;
- hallazgos_researcher: recomendaciones técnicas y fuentes consultadas (puede
  ser null si el Researcher no encontró evidencia);
- resultado_tester_previo: si esto no es null, significa que ya intentaste
  esta misma tarea antes, el Tester corrió build/tests/lint y algo falló.
  Contiene los checks ejecutados con su stdout/stderr. Usalo para corregir
  el problema puntual -- no repitas el mismo cambio que ya falló.
- memoria_previa_del_proyecto: puede ser null. Si no lo es, son decisiones,
  convenciones y bugs ya investigados en corridas anteriores sobre este
  mismo repositorio. Mantené coherencia con decisiones previas salvo que
  el pedido actual las contradiga explícitamente.

Reglas:
- Usá read_file para ver el contenido actual de un archivo antes de
  modificarlo. write_file reemplaza el contenido completo del archivo, así
  que primero leé, después generá el contenido entero modificado y recién
  ahí escribilo.
- No inventes APIs, decorators, comandos ni convenciones que no estén
  respaldadas por los hallazgos del Explorer o del Researcher.
- No modifiques archivos que no hayan sido identificados como relevantes o
  justificados por la evidencia disponible.
- No repitas la misma lectura o escritura si ya la hiciste.
- Si el pedido es ambiguo o no hay evidencia suficiente para decidir con
  confianza, no escribas código al azar: respondé igual con el JSON final,
  marcando evidence_sufficient en false y explicando en risks_or_notes qué
  información falta.
- Priorizá actuar: en cuanto tengas evidencia suficiente para modificar un
  archivo, llamá a write_file. No seguas leyendo archivos "por las dudas"
  una vez que ya sabés qué cambio hay que hacer. Un resumen o plan de lo
  que harías, sin haber llamado a write_file, NO es una implementación
  válida -- en ese caso evidence_sufficient debe ser false y changes debe
  quedar vacío, aunque hayas juntado evidencia de sobra.
  - Usá run_command solamente cuando sea necesario para completar la
    implementación, por ejemplo para generar artefactos o migraciones.
  - No ejecutes tests generales: esa responsabilidad pertenece al Tester.
  - No ejecutes comandos que no estén respaldados por la evidencia del
    repositorio.
- Cuando termines -- hayas aplicado los cambios o decidido que no podés
  continuar -- respondé con un único objeto JSON, sin texto alrededor, con
  esta forma exacta:
  {
    "evidence_sufficient": true,
    "summary": "resumen breve de qué se implementó",
    "changes": [
      {"file": "...", "reason": "..."}
    ],
    "risks_or_notes": ["..."]
  }
"""

    FINAL_ITERATION_REMINDER = """
AVISO DEL SISTEMA: esta es la última iteración disponible, no podés usar
más tools -- ya no podés llamar a write_file. Respondé ahora ÚNICAMENTE
con un objeto JSON (sin texto antes ni después) con esta forma exacta:
{
  "evidence_sufficient": true,
  "summary": "resumen breve de qué se implementó",
  "changes": [
    {"file": "...", "reason": "..."}
  ],
  "risks_or_notes": ["..."]
}
Si NO llegaste a llamar a write_file en ningún momento, no describas un
plan: poné evidence_sufficient en false, changes en una lista vacía, y
explicá en risks_or_notes que no se aplicaron cambios reales.
"""

    def __init__(self, tool_executor: ToolExecutor):
        self.tool_executor = tool_executor

    def run(self, task_state: TaskState) -> SubagentResult:
        client = get_client()
        task_state.set_phase("implementation")

        explorer_result = task_state.last_result_of("explorer")

        if explorer_result is None:
            task_state.status = "needs_help"

            return SubagentResult(
                subagent="implementer",
                summary=(
                    "No se pudo implementar porque falta el resultado "
                    "del Explorer."
                ),
                data={
                    "evidence_sufficient": False,
                    "reason": "missing_explorer_result",
                },
                sources=[],
            )

        researcher_result = task_state.last_result_of("researcher")
        tester_result = task_state.last_result_of("tester")

        memory = task_state.project_memory
        used_memory = bool(memory and memory.has_prior_knowledge())

        context = {
            "pedido_original": task_state.original_request,
            "hallazgos_explorer": explorer_result.data,
            "hallazgos_researcher": (
                researcher_result.data if researcher_result else None
            ),
            "resultado_tester_previo": (
                tester_result.data if tester_result else None
            ),
            "memoria_previa_del_proyecto": (
                memory.as_context() if used_memory else None
            ),
        }

        messages = [
            {
                "role": "system",
                "content": self.SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": json.dumps(context, ensure_ascii=False),
            },
        ]

        for iteration in range(1, self.MAX_ITERATIONS + 1):
            is_last_iteration = iteration == self.MAX_ITERATIONS

            if is_last_iteration:
                messages.append({
                    "role": "user",
                    "content": self.FINAL_ITERATION_REMINDER,
                })

            response = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                tools=IMPLEMENTER_TOOLS,
                tool_choice="none" if is_last_iteration else "auto",
            )

            assistant_message = response.choices[0].message

            if not assistant_message.tool_calls:
                task_state.record_iterations("implementer", iteration)

                return self._finalize(
                    task_state,
                    assistant_message.content,
                    iteration,
                    used_memory,
                )

            messages.append(assistant_message)

            for tool_call in assistant_message.tool_calls:
                tool_name = tool_call.function.name

                try:
                    tool_args = json.loads(
                        tool_call.function.arguments or "{}"
                    )
                except json.JSONDecodeError as exc:
                    tool_result = (
                        "Error: los argumentos de la tool no son JSON "
                        f"válido: {exc}"
                    )

                    task_state.record_observation(tool_result)

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
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
                        f"Implementer repitió {tool_name}({tool_args})."
                    )

                    tool_result = (
                        "AVISO DEL SISTEMA: esta misma tool call ya fue "
                        "ejecutada dos veces. No la repitas. Usá otra "
                        "estrategia o entregá el JSON final."
                    )
                else:
                    tool_result = self.tool_executor.execute(
                        subagent="implementer",
                        tool_name=tool_name,
                        arguments=tool_args,
                        task_state=task_state,
                        allowed_tools=ALLOWED_TOOLS,
                    )

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": tool_result,
                })

        task_state.record_iterations(
            "implementer",
            self.MAX_ITERATIONS,
        )

        task_state.record_observation(
            f"Implementer alcanzó el límite de "
            f"{self.MAX_ITERATIONS} iteraciones."
        )

        return SubagentResult(
            subagent="implementer",
            summary=(
                "El Implementer no pudo concluir dentro del límite "
                "de iteraciones."
            ),
            data={"evidence_sufficient": False},
            sources=["repository", "memory"] if used_memory else ["repository"],
        )

    @staticmethod
    def _finalize(
        task_state: TaskState,
        content: str,
        iterations: int,
        used_memory: bool,
    ) -> SubagentResult:
        try:
            data = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            task_state.record_observation(
                "Implementer no devolvió JSON válido; "
                "se guardó como texto libre."
            )
            data = {
                "evidence_sufficient": False,
                "summary": "",
                "changes": [],
                "risks_or_notes": [],
                "resumen_libre": content,
            }

        # Garantiza que siempre se trabaje con un diccionario.
        if not isinstance(data, dict):
            data = {
                "evidence_sufficient": False,
                "summary": "",
                "changes": [],
                "risks_or_notes": [
                    "La respuesta final del Implementer no tenía "
                    "el formato esperado."
                ],
            }

        # Archivos que realmente fueron modificados mediante write_file.
        actual_modified_files = set(task_state.files_modified)

        # Si no hubo escrituras reales, no se acepta que el modelo
        # declare cambios solamente en su respuesta.
        if not actual_modified_files:
            data["evidence_sufficient"] = False
            data["changes"] = []

            notes = data.get("risks_or_notes", [])

            if not isinstance(notes, list):
                notes = []

            notes.append(
                "No se registraron escrituras reales en el workspace."
            )

            data["risks_or_notes"] = notes

        changes = data.get("changes", [])

        if not isinstance(changes, list):
            changes = []
            data["changes"] = changes

        sources = (
            ["repository", "memory"]
            if used_memory
            else ["repository"]
        )

        return SubagentResult(
            subagent="implementer",
            summary=(
                f"Implementación completada en {iterations} "
                f"iteraciones ({len(actual_modified_files)} "
                f"archivo(s) modificado(s) realmente)."
            ),
            data=data,
            sources=sources,
        )
