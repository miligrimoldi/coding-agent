import json

from llm_client import get_client, MODEL
from task_state import TaskState, SubagentResult
from tool_executor import ToolExecutor
from tools.loader import get_tools_for


ALLOWED_TOOLS = ["read_file", "list_files"]
REVIEWER_TOOLS = get_tools_for(ALLOWED_TOOLS)


class Reviewer:
    MAX_ITERATIONS = 7
    REPEAT_THRESHOLD = 2

    SYSTEM_PROMPT = """
Sos el subagente Reviewer dentro de un sistema multiagente de desarrollo
de código.

Tu responsabilidad es revisar los cambios que aplicó el Implementer y
determinar si responden al pedido original del usuario.

Recibís, en el primer mensaje, un JSON con:
- pedido_original: el pedido del usuario;
- archivos_modificados: lista real de paths (relativos al workspace) que
  quedaron escritos, según el registro del sistema;
- cambios_declarados: lo que el Implementer dice haber hecho (summary,
  changes con motivo por archivo, risks_or_notes);
- resultado_tester: los checks de build/tests/lint que corrió el Tester
  y si pasaron (puede ser null si el Tester no corrió).

Reglas:
- Usá read_file para leer el contenido actual de los archivos en
  archivos_modificados y confirmar que el cambio declarado realmente está
  aplicado y es coherente con el pedido original.
- No apruebes cambios que no leíste.
- Si archivos_modificados no coincide con lo que describe cambios_declarados
  (archivos de más, de menos, o razones que no se condicen con el contenido
  real), marcalo como issue.
- Si el Tester reportó fallas (all_passed en false), normalmente no se
  aprueba el cambio, salvo que el pedido explícitamente no dependa de esos
  checks -- en ese caso explicá por qué igual lo aprobás.
- No inventes contenido de archivos que no leíste.
- Cuando termines, respondé con un único objeto JSON, sin texto alrededor,
  con esta forma exacta:
  {
    "approved": true,
    "matches_request": true,
    "summary": "resumen breve de la revisión",
    "issues": ["..."],
    "files_reviewed": ["..."]
  }
"""

    FINAL_ITERATION_REMINDER = """
AVISO DEL SISTEMA: esta es la última iteración disponible, no podés usar
más tools. Respondé ahora ÚNICAMENTE con un objeto JSON (sin texto antes
ni después) con esta forma exacta, en base a lo que hayas podido revisar:
{
  "approved": true,
  "matches_request": true,
  "summary": "resumen breve de la revisión",
  "issues": ["..."],
  "files_reviewed": ["..."]
}
"""

    def __init__(self, tool_executor: ToolExecutor):
        self.tool_executor = tool_executor

    def run(self, task_state: TaskState) -> SubagentResult:
        client = get_client()
        task_state.set_phase("review")

        implementer_result = task_state.last_result_of("implementer")

        if implementer_result is None:
            task_state.status = "needs_help"

            return SubagentResult(
                subagent="reviewer",
                summary=(
                    "No se pudo revisar porque falta el resultado "
                    "del Implementer."
                ),
                data={
                    "approved": False,
                    "reason": "missing_implementer_result",
                },
                sources=[],
            )

        tester_result = task_state.last_result_of("tester")

        context = {
            "pedido_original": task_state.original_request,
            "archivos_modificados": task_state.files_modified,
            "cambios_declarados": implementer_result.data,
            "resultado_tester": (
                tester_result.data if tester_result else None
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
                tools=REVIEWER_TOOLS,
                tool_choice="none" if is_last_iteration else "auto",
            )

            assistant_message = response.choices[0].message

            if not assistant_message.tool_calls:
                task_state.record_iterations("reviewer", iteration)

                return self._finalize(
                    task_state,
                    assistant_message.content,
                    iteration,
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
                    subagent="reviewer",
                    tool_name=tool_name,
                    args=tool_args,
                    threshold=self.REPEAT_THRESHOLD,
                ):
                    task_state.record_tool_call(
                        subagent="reviewer",
                        tool_name=tool_name,
                        args=tool_args,
                        outcome="blocked_repeat",
                    )

                    task_state.record_observation(
                        f"Reviewer repitió {tool_name}({tool_args})."
                    )

                    tool_result = (
                        "AVISO DEL SISTEMA: esta misma tool call ya fue "
                        "ejecutada dos veces. No la repitas. Usá otra "
                        "estrategia o entregá el JSON final."
                    )
                else:
                    tool_result = self.tool_executor.execute(
                        subagent="reviewer",
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
            "reviewer",
            self.MAX_ITERATIONS,
        )

        task_state.record_observation(
            f"Reviewer alcanzó el límite de "
            f"{self.MAX_ITERATIONS} iteraciones."
        )

        return SubagentResult(
            subagent="reviewer",
            summary=(
                "El Reviewer no pudo concluir dentro del límite "
                "de iteraciones."
            ),
            data={"approved": False},
            sources=["repository"],
        )

    @staticmethod
    def _finalize(
        task_state: TaskState,
        content: str,
        iterations: int,
    ) -> SubagentResult:
        try:
            data = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            task_state.record_observation(
                "Reviewer no devolvió JSON válido; "
                "se guardó como texto libre."
            )
            data = {
                "resumen_libre": content,
                "approved": False,
            }

        approved = (
            bool(data.get("approved"))
            if isinstance(data, dict)
            else False
        )

        return SubagentResult(
            subagent="reviewer",
            summary=(
                f"Revisión completada en {iterations} iteraciones "
                f"({'aprobado' if approved else 'no aprobado'})."
            ),
            data=data,
            sources=["repository"],
        )
